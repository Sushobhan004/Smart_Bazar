from django.db import transaction
from rest_framework import viewsets, permissions, status, views
from rest_framework.response import Response
from apps.inventory.models import (
    Inventory, StockTransaction, StockAdjustment,
    StockNotification, LOW_STOCK_THRESHOLD, sync_stock_notification
)
from apps.inventory.serializers import InventorySerializer, StockTransactionSerializer, StockAdjustmentSerializer
from apps.products.models import Product

class InventoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = InventorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        low_stock = self.request.query_params.get('low_stock')

        qs = Inventory.objects.select_related('product', 'shop').all()
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        elif user.is_shop_owner():
            qs = qs.filter(shop__owner=user)
        elif user.is_worker():
            qs = qs.filter(shop__memberships__user=user)

        if low_stock == 'true':
            qs = [item for item in qs if item.is_low_stock]
            return qs

        return qs

class StockAdjustmentView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        user = request.user
        product_id = request.data.get('product_id')
        new_quantity = request.data.get('new_quantity')
        reason = request.data.get('reason', 'Physical stock audit adjustment')

        if product_id is None or new_quantity is None:
            return Response({'error': 'product_id and new_quantity are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_qty = float(new_quantity)
        except ValueError:
            return Response({'error': 'new_quantity must be a valid number.'}, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            product = Product.objects.select_for_update().get(id=product_id)
            inv, _ = Inventory.objects.select_for_update().get_or_create(
                product=product,
                defaults={'shop': product.shop, 'current_stock': 0.00}
            )
            old_qty = float(inv.current_stock)
            diff = new_qty - old_qty
            inv.current_stock = new_qty
            inv.save()

            adjustment = StockAdjustment.objects.create(
                shop=product.shop,
                product=product,
                adjusted_by=user,
                old_quantity=old_qty,
                new_quantity=new_qty,
                reason=reason
            )

            StockTransaction.objects.create(
                shop=product.shop,
                product=product,
                tx_type=StockTransaction.TxType.ADJUSTMENT,
                quantity=diff,
                balance_after=new_qty,
                reference_id=str(adjustment.id),
                performed_by=user,
                notes=reason
            )

        return Response({
            'message': 'Stock successfully adjusted.',
            'product': product.name,
            'old_stock': old_qty,
            'new_stock': new_qty
        }, status=status.HTTP_200_OK)

class StockTransactionListView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        shop_id = request.query_params.get('shop_id')
        product_id = request.query_params.get('product_id')

        qs = StockTransaction.objects.select_related('product', 'performed_by').all()
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        elif user.is_shop_owner():
            qs = qs.filter(shop__owner=user)
        elif user.is_worker():
            qs = qs.filter(shop__memberships__user=user)

        if product_id:
            qs = qs.filter(product_id=product_id)

        serializer = StockTransactionSerializer(qs[:100], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class LowStockAlertsView(views.APIView):
    """Automatic low-stock (< 15 units) notifications for Shop Owner and Worker/Cashier dashboards."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        shop_id = request.query_params.get('shop_id')

        # Ensure every inventory below 15 has an up-to-date StockNotification
        inv_qs = Inventory.objects.select_related('product', 'shop').filter(
            product__is_active=True,
            current_stock__lt=LOW_STOCK_THRESHOLD
        )
        if shop_id and shop_id != 'null':
            inv_qs = inv_qs.filter(shop_id=shop_id)
        for inv in inv_qs:
            sync_stock_notification(inv)

        notif_qs = StockNotification.objects.select_related(
            'product', 'product__category', 'shop'
        ).prefetch_related('product__barcodes').filter(
            is_resolved=False,
            product__is_active=True
        )
        if shop_id and shop_id != 'null':
            notif_qs = notif_qs.filter(shop_id=shop_id)

        alerts = []
        unread_owner = 0
        unread_worker = 0
        for n in notif_qs:
            if not n.acknowledged_by_owner:
                unread_owner += 1
            if not n.acknowledged_by_worker:
                unread_worker += 1
            first_bc = n.product.barcodes.first()
            alerts.append({
                'id': str(n.id),
                'product_id': str(n.product_id),
                'product_name': n.product.name,
                'barcode': first_bc.barcode if first_bc else n.product.sku,
                'category': n.product.category.name if n.product.category else 'General',
                'unit': n.product.unit,
                'selling_price': float(n.product.selling_price),
                'current_stock': float(n.current_stock),
                'threshold': n.threshold,
                'severity': n.severity,
                'title': n.title,
                'message': n.message,
                'acknowledged_by_owner': n.acknowledged_by_owner,
                'acknowledged_by_worker': n.acknowledged_by_worker,
                'updated_at': n.updated_at.strftime('%d %b %Y, %I:%M %p'),
            })

        return Response({
            'threshold': LOW_STOCK_THRESHOLD,
            'count': len(alerts),
            'unread_owner_count': unread_owner,
            'unread_worker_count': unread_worker,
            'alerts': alerts,
        }, status=status.HTTP_200_OK)


class AcknowledgeLowStockAlertsView(views.APIView):
    """Marks low-stock alerts as seen/acknowledged for Owner or Worker dashboard."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        role = str(request.data.get('role', 'OWNER')).upper()
        notification_id = request.data.get('notification_id')

        qs = StockNotification.objects.filter(is_resolved=False)
        if notification_id:
            qs = qs.filter(id=notification_id)

        if role == 'WORKER':
            qs.update(acknowledged_by_worker=True)
        else:
            qs.update(acknowledged_by_owner=True)

        return Response({'success': True}, status=status.HTTP_200_OK)


