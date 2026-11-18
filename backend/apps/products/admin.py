from django.contrib import admin
from .models import Category, Product, ProductBarcode, ProductVariant

class ProductBarcodeInline(admin.TabularInline):
    model = ProductBarcode
    extra = 1

class ProductVariantInline(admin.TabularInline):
    model = ProductVariant
    extra = 1

@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'icon', 'created_at')
    list_filter = ('shop',)
    search_fields = ('name', 'description')

@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'category', 'selling_price', 'mrp', 'tax_rate', 'unit', 'min_stock_alert')
    list_filter = ('shop', 'category', 'unit', 'tax_rate')
    search_fields = ('name', 'sku', 'brand', 'hsn_code', 'barcodes__barcode')
    inlines = [ProductBarcodeInline, ProductVariantInline]

@admin.register(ProductBarcode)
class ProductBarcodeAdmin(admin.ModelAdmin):
    list_display = ('barcode', 'product', 'format', 'is_primary')
    list_filter = ('format', 'is_primary')
    search_fields = ('barcode', 'product__name')

@admin.register(ProductVariant)
class ProductVariantAdmin(admin.ModelAdmin):
    list_display = ('name', 'product', 'sku', 'barcode', 'price_difference')
    search_fields = ('name', 'sku', 'barcode', 'product__name')

