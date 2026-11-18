from django.contrib import admin
from .models import Sale, SaleItem, Invoice, Payment, Return, ReturnItem

class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ('product_name', 'barcode', 'quantity', 'unit_price', 'tax_rate', 'tax_amount', 'discount', 'total_price')

class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0
    readonly_fields = ('amount', 'payment_method', 'transaction_id', 'is_success', 'created_at')

@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('bill_number', 'shop', 'worker', 'customer', 'final_total', 'payment_method', 'payment_status', 'created_at')
    list_filter = ('payment_status', 'payment_method', 'shop', 'created_at')
    search_fields = ('bill_number', 'customer__full_name', 'customer__phone_number', 'guest_phone', 'idempotency_key')
    readonly_fields = ('bill_number', 'subtotal', 'tax_amount', 'discount_amount', 'round_off', 'final_total', 'idempotency_key', 'created_at', 'updated_at')
    inlines = [SaleItemInline, PaymentInline]

@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('product_name', 'sale', 'quantity', 'unit_price', 'total_price', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('product_name', 'barcode', 'sale__bill_number')

@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ('invoice_number', 'sale', 'sent_to_email', 'sent_at', 'created_at')
    search_fields = ('invoice_number', 'sale__bill_number', 'sent_to_email')

@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ('sale', 'amount', 'payment_method', 'transaction_id', 'is_success', 'created_at')
    list_filter = ('payment_method', 'is_success', 'created_at')
    search_fields = ('transaction_id', 'sale__bill_number')

@admin.register(Return)
class ReturnAdmin(admin.ModelAdmin):
    list_display = ('return_number', 'sale', 'shop', 'worker', 'refund_amount', 'refund_method', 'created_at')
    list_filter = ('refund_method', 'shop', 'created_at')
    search_fields = ('return_number', 'sale__bill_number', 'reason')

