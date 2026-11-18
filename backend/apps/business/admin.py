from django.contrib import admin
from .models import Expense, CashRegister, CashShift, DailySalesSummary

@admin.register(Expense)
class ExpenseAdmin(admin.ModelAdmin):
    list_display = ('title', 'shop', 'category', 'amount', 'expense_date', 'recorded_by')
    list_filter = ('category', 'shop', 'expense_date')
    search_fields = ('title', 'notes', 'recorded_by__username')

@admin.register(CashRegister)
class CashRegisterAdmin(admin.ModelAdmin):
    list_display = ('name', 'shop', 'current_balance')
    list_filter = ('shop',)
    search_fields = ('name', 'shop__name')

@admin.register(CashShift)
class CashShiftAdmin(admin.ModelAdmin):
    list_display = ('worker', 'shop', 'status', 'start_time', 'end_time', 'opening_cash', 'cash_sales', 'actual_closing_cash', 'difference')
    list_filter = ('status', 'shop', 'start_time')
    search_fields = ('worker__username', 'notes')

@admin.register(DailySalesSummary)
class DailySalesSummaryAdmin(admin.ModelAdmin):
    list_display = ('date', 'shop', 'total_bills', 'total_revenue', 'gross_profit', 'net_profit')
    list_filter = ('shop', 'date')
    search_fields = ('shop__name',)

