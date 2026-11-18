from decimal import Decimal
from rest_framework import serializers
from apps.billing.models import Sale, SaleItem, Invoice, Payment, Return, ReturnItem

class SaleItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = SaleItem
        fields = [
            'id', 'product', 'product_name', 'barcode', 'quantity',
            'unit_price', 'tax_rate', 'tax_amount', 'discount', 'total_price'
        ]

class InvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoice
        fields = ['id', 'invoice_number', 'qr_data', 'pdf_file', 'created_at']

class SaleSerializer(serializers.ModelSerializer):
    items = SaleItemSerializer(many=True, read_only=True)
    invoice = InvoiceSerializer(read_only=True)
    shop_name = serializers.ReadOnlyField(source='shop.name')
    worker_name = serializers.ReadOnlyField(source='worker.username')
    customer_name = serializers.ReadOnlyField(source='customer.full_name')

    class Meta:
        model = Sale
        fields = [
            'id', 'shop', 'shop_name', 'worker', 'worker_name', 'customer', 'customer_name',
            'bill_number', 'is_guest', 'guest_name', 'guest_phone',
            'subtotal', 'tax_amount', 'discount_amount', 'round_off', 'final_total',
            'payment_method', 'payment_status', 'idempotency_key', 'items', 'invoice',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class CartItemInputSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=Decimal('0.01'))
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=Decimal('0.00'))

class CreateSaleRequestSerializer(serializers.Serializer):
    shop_id = serializers.UUIDField()
    customer_id = serializers.UUIDField(required=False, allow_null=True)
    is_guest = serializers.BooleanField(default=False)
    guest_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    guest_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    items = CartItemInputSerializer(many=True)
    payment_method = serializers.ChoiceField(choices=Sale.PaymentMethod.choices, default=Sale.PaymentMethod.CASH)
    idempotency_key = serializers.CharField(max_length=128)
    notes = serializers.CharField(required=False, allow_blank=True)
    voucher_code = serializers.CharField(max_length=50, required=False, allow_blank=True)

