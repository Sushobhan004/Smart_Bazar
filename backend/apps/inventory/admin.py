from django.contrib import admin
from .models import Inventory, StockTransaction, StockBatch, StockAdjustment, StockNotification

@admin.register(Inventory)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ('product', 'shop', 'current_stock', 'reorder_level', 'is_low_stock', 'is_out_of_stock', 'last_restocked_at')
    list_filter = ('shop', 'reorder_level')
    search_fields = ('product__name', 'product__sku', 'shop__name')
    readonly_fields = ('last_restocked_at',)

@admin.register(StockTransaction)
class StockTransactionAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'tx_type', 'product', 'quantity', 'balance_after', 'reference_id', 'shop', 'performed_by')
    list_filter = ('tx_type', 'shop', 'created_at')
    search_fields = ('product__name', 'reference_id', 'notes', 'performed_by__username')
    readonly_fields = ('created_at', 'updated_at')

@admin.register(StockBatch)
class StockBatchAdmin(admin.ModelAdmin):
    list_display = ('batch_number', 'product', 'quantity', 'purchase_date', 'expiry_date', 'cost_price')
    list_filter = ('expiry_date', 'purchase_date')
    search_fields = ('batch_number', 'product__name')

@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ('product', 'shop', 'old_quantity', 'new_quantity', 'adjusted_by', 'created_at')
    list_filter = ('shop', 'created_at')
    search_fields = ('product__name', 'reason', 'adjusted_by__username')

@admin.register(StockNotification)
class StockNotificationAdmin(admin.ModelAdmin):
    list_display = ('title', 'shop', 'current_stock', 'threshold', 'severity', 'is_resolved', 'acknowledged_by_owner', 'acknowledged_by_worker', 'updated_at')
    list_filter = ('severity', 'is_resolved', 'shop')
    search_fields = ('title', 'message', 'product__name')

