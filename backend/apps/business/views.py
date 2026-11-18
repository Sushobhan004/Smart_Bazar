from decimal import Decimal
from django.db.models import Sum, Count, F, Q
from django.utils import timezone
from rest_framework import viewsets, permissions, views, status
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.business.models import Expense, CashRegister, CashShift, DailySalesSummary
from apps.business.serializers import ExpenseSerializer, CashShiftSerializer, CloseShiftSerializer
from apps.billing.models import Sale, SaleItem
from apps.products.models import Product
from apps.inventory.models import Inventory, LOW_STOCK_THRESHOLD, sync_stock_notification

class ExpenseViewSet(viewsets.ModelViewSet):
    serializer_class = ExpenseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        qs = Expense.objects.select_related('recorded_by').all()
        if shop_id:
            return qs.filter(shop_id=shop_id)
        if user.is_shop_owner():
            return qs.filter(shop__owner=user)
        return qs

    def perform_create(self, serializer):
        serializer.save(recorded_by=self.request.user)

class CashShiftViewSet(viewsets.ModelViewSet):
    serializer_class = CashShiftSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        qs = CashShift.objects.select_related('worker', 'shop').all()
        if shop_id:
            return qs.filter(shop_id=shop_id)
        if user.is_shop_owner():
            return qs.filter(shop__owner=user)
        if user.is_worker():
            return qs.filter(worker=user)
        return qs

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        shift = self.get_object()
        if shift.status == CashShift.Status.CLOSED:
            return Response({'error': 'Shift is already closed.'}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CloseShiftSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        actual_cash = serializer.validated_data['actual_closing_cash']
        notes = serializer.validated_data.get('notes', '')

        # Calculate sales during shift
        sales = Sale.objects.filter(
            shop=shift.shop,
            worker=shift.worker,
            created_at__gte=shift.start_time,
            payment_status=Sale.PaymentStatus.COMPLETED
        )
        cash_sales = sales.filter(payment_method=Sale.PaymentMethod.CASH).aggregate(total=Sum('final_total'))['total'] or Decimal('0.00')
        upi_sales = sales.filter(payment_method=Sale.PaymentMethod.UPI).aggregate(total=Sum('final_total'))['total'] or Decimal('0.00')

        shift.cash_sales = cash_sales
        shift.upi_sales = upi_sales
        shift.actual_closing_cash = actual_cash
        shift.expected_closing_cash = shift.opening_cash + cash_sales - shift.cash_refunds
        shift.difference = shift.actual_closing_cash - shift.expected_closing_cash
        shift.status = CashShift.Status.CLOSED
        shift.end_time = timezone.now()
        shift.notes = notes
        shift.save()

        return Response(CashShiftSerializer(shift).data, status=status.HTTP_200_OK)

class BusinessReportsView(views.APIView):
    """Analytics for Shop Owner and Super Admin."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        shop_id = request.query_params.get('shop_id')

        sales_qs = Sale.objects.filter(payment_status=Sale.PaymentStatus.COMPLETED)
        products_qs = Product.objects.filter(is_active=True)
        inventory_qs = Inventory.objects.all()

        if shop_id:
            sales_qs = sales_qs.filter(shop_id=shop_id)
            products_qs = products_qs.filter(shop_id=shop_id)
            inventory_qs = inventory_qs.filter(shop_id=shop_id)
        elif user.is_shop_owner():
            sales_qs = sales_qs.filter(shop__owner=user)
            products_qs = products_qs.filter(shop__owner=user)
            inventory_qs = inventory_qs.filter(shop__owner=user)

        now = timezone.now()
        today_sales = sales_qs.filter(created_at__date=now.date())
        today_rev = today_sales.aggregate(total=Sum('final_total'))['total'] or Decimal('0.00')
        today_cash = today_sales.filter(payment_method=Sale.PaymentMethod.CASH).aggregate(total=Sum('final_total'))['total'] or Decimal('0.00')
        today_upi = today_sales.filter(payment_method=Sale.PaymentMethod.UPI).aggregate(total=Sum('final_total'))['total'] or Decimal('0.00')
        today_bills = today_sales.count()

        total_rev = sales_qs.aggregate(total=Sum('final_total'))['total'] or Decimal('0.00')
        total_bills = sales_qs.count()

        # Best-selling products
        best_sellers = (
            SaleItem.objects.filter(sale__in=sales_qs)
            .values('product_name')
            .annotate(total_qty=Sum('quantity'), total_amt=Sum('total_price'))
            .order_by('-total_amt')[:5]
        )

        # Inventory statistics (< 15 units alert rule)
        low_stock_items = [inv for inv in inventory_qs.select_related('product', 'product__category') if inv.is_low_stock]
        for inv in low_stock_items:
            sync_stock_notification(inv)
        low_stock_alerts = [
            {
                'product_id': str(inv.product_id),
                'product_name': inv.product.name,
                'category': inv.product.category.name if inv.product.category else 'General',
                'unit': inv.product.unit,
                'current_stock': float(inv.current_stock),
                'threshold': LOW_STOCK_THRESHOLD,
                'severity': 'CRITICAL' if inv.current_stock <= 0 else 'WARNING',
                'message': f"Only {int(inv.current_stock)} {inv.product.unit} left (below {LOW_STOCK_THRESHOLD})"
            }
            for inv in sorted(low_stock_items, key=lambda x: x.current_stock)
        ]
        low_stock_count = len(low_stock_items)
        out_of_stock_count = sum(1 for inv in low_stock_items if inv.is_out_of_stock)

        return Response({
            'today_revenue': float(today_rev),
            'today_cash': float(today_cash),
            'today_upi': float(today_upi),
            'today_bills': today_bills,
            'total_revenue': float(total_rev),
            'total_bills': total_bills,
            'total_products': products_qs.count(),
            'low_stock_threshold': LOW_STOCK_THRESHOLD,
            'low_stock_count': low_stock_count,
            'out_of_stock_count': out_of_stock_count,
            'low_stock_alerts': low_stock_alerts,
            'best_sellers': list(best_sellers),
        }, status=status.HTTP_200_OK)

