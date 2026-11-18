from rest_framework import serializers
from apps.suppliers.models import Supplier, Purchase, PurchaseItem, SupplierPayment

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'shop', 'company_name', 'contact_person', 'phone', 'email', 'address', 'gstin']

class PurchaseItemSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')

    class Meta:
        model = PurchaseItem
        fields = ['id', 'product', 'product_name', 'quantity', 'unit_cost', 'tax_rate', 'total_cost', 'batch_number', 'expiry_date']

class PurchaseSerializer(serializers.ModelSerializer):
    items = PurchaseItemSerializer(many=True, read_only=True)
    supplier_name = serializers.ReadOnlyField(source='supplier.company_name')

    class Meta:
        model = Purchase
        fields = ['id', 'shop', 'supplier', 'supplier_name', 'invoice_number', 'purchase_date', 'total_amount', 'paid_amount', 'payment_status', 'goods_status', 'items']

