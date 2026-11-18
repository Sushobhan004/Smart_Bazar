from rest_framework import serializers
from apps.products.models import Category, Product, ProductBarcode, ProductVariant
from apps.inventory.models import Inventory

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'shop', 'name', 'icon', 'description']

class ProductBarcodeSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductBarcode
        fields = ['id', 'barcode', 'format', 'is_primary']

class ProductVariantSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductVariant
        fields = ['id', 'name', 'sku', 'barcode', 'price_difference']

class ProductSerializer(serializers.ModelSerializer):
    barcodes = ProductBarcodeSerializer(many=True, read_only=True)
    barcode_list = serializers.ListField(child=serializers.CharField(), write_only=True, required=False)
    initial_stock = serializers.DecimalField(max_digits=10, decimal_places=2, write_only=True, required=False, default=0.00)
    current_stock = serializers.SerializerMethodField()
    category_name = serializers.ReadOnlyField(source='category.name')
    primary_barcode = serializers.ReadOnlyField()

    class Meta:
        model = Product
        fields = [
            'id', 'shop', 'category', 'category_name', 'name', 'sku', 'description',
            'brand', 'purchase_price', 'selling_price', 'mrp', 'tax_rate', 'hsn_code',
            'unit', 'min_stock_alert', 'is_active', 'barcodes', 'barcode_list',
            'initial_stock', 'current_stock', 'primary_barcode', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_current_stock(self, obj):
        inv = getattr(obj, 'inventory', None)
        return float(inv.current_stock) if inv else 0.0

    def create(self, validated_data):
        barcodes_data = validated_data.pop('barcode_list', [])
        initial_stock = validated_data.pop('initial_stock', 0.00)
        product = Product.objects.create(**validated_data)
        
        # Create barcodes
        is_first = True
        for code in barcodes_data:
            ProductBarcode.objects.create(
                product=product,
                barcode=code.strip(),
                is_primary=is_first
            )
            is_first = False

        # Create linked inventory record
        Inventory.objects.create(
            shop=product.shop,
            product=product,
            current_stock=initial_stock,
            reorder_level=product.min_stock_alert
        )
        return product

