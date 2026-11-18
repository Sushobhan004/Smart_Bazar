from rest_framework import serializers
from apps.inventory.models import Inventory, StockTransaction, StockAdjustment, StockBatch

class InventorySerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    product_sku = serializers.ReadOnlyField(source='product.sku')
    selling_price = serializers.ReadOnlyField(source='product.selling_price')
    is_low_stock = serializers.ReadOnlyField()
    is_out_of_stock = serializers.ReadOnlyField()

    class Meta:
        model = Inventory
        fields = [
            'id', 'shop', 'product', 'product_name', 'product_sku', 'selling_price',
            'current_stock', 'reorder_level', 'is_low_stock', 'is_out_of_stock',
            'last_restocked_at', 'updated_at'
        ]

class StockTransactionSerializer(serializers.ModelSerializer):
    product_name = serializers.ReadOnlyField(source='product.name')
    performer_name = serializers.ReadOnlyField(source='performed_by.username')

    class Meta:
        model = StockTransaction
        fields = [
            'id', 'shop', 'product', 'product_name', 'tx_type', 'quantity',
            'balance_after', 'reference_id', 'performed_by', 'performer_name',
            'notes', 'created_at'
        ]

class StockAdjustmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = StockAdjustment
        fields = ['id', 'shop', 'product', 'adjusted_by', 'old_quantity', 'new_quantity', 'reason', 'created_at']
        read_only_fields = ['id', 'adjusted_by', 'created_at']

