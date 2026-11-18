from rest_framework import viewsets, permissions
from apps.suppliers.models import Supplier, Purchase
from apps.suppliers.serializers import SupplierSerializer, PurchaseSerializer

class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        qs = Supplier.objects.all()
        if shop_id:
            return qs.filter(shop_id=shop_id)
        if user.is_shop_owner():
            return qs.filter(shop__owner=user)
        return qs

class PurchaseViewSet(viewsets.ModelViewSet):
    serializer_class = PurchaseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        qs = Purchase.objects.select_related('supplier', 'shop').prefetch_related('items').all()
        if shop_id:
            return qs.filter(shop_id=shop_id)
        if user.is_shop_owner():
            return qs.filter(shop__owner=user)
        return qs

