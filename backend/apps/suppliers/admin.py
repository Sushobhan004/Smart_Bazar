from django.contrib import admin
from .models import Supplier, Purchase, PurchaseItem, SupplierPayment

class PurchaseItemInline(admin.TabularInline):
    model = PurchaseItem
    extra = 1

class SupplierPaymentInline(admin.TabularInline):
    model = SupplierPayment
    extra = 0

@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'shop', 'contact_person', 'phone', 'email', 'gstin')
    list_filter = ('shop',)
    search_fields = ('company_name', 'contact_person', 'phone', 'email')

@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'supplier', 'shop', 'purchase_date', 'total_amount', 'paid_amount', 'payment_status', 'goods_status')
    list_filter = ('payment_status', 'goods_status', 'shop', 'purchase_date')
    search_fields = ('invoice_number', 'supplier__company_name')
    inlines = [PurchaseItemInline, SupplierPaymentInline]

@admin.register(PurchaseItem)
class PurchaseItemAdmin(admin.ModelAdmin):
    list_display = ('purchase', 'product', 'quantity', 'unit_cost', 'total_cost', 'batch_number')
    search_fields = ('product__name', 'batch_number', 'purchase__invoice_number')

@admin.register(SupplierPayment)
class SupplierPaymentAdmin(admin.ModelAdmin):
    list_display = ('purchase', 'amount', 'payment_method', 'payment_date', 'reference_number')
    search_fields = ('reference_number', 'purchase__invoice_number')

