import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel

class Expense(TimeStampedModel):
    class Category(models.TextChoices):
        RENT = 'RENT', 'Shop Rent'
        UTILITIES = 'UTILITIES', 'Electricity & Water'
        SALARY = 'SALARY', 'Staff Wages'
        SUPPLIES = 'SUPPLIES', 'Store Supplies & Packaging'
        MAINTENANCE = 'MAINTENANCE', 'Repairs & Maintenance'
        MARKETING = 'MARKETING', 'Promotion & Ads'
        OTHER = 'OTHER', 'Miscellaneous'

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='expenses')
    title = models.CharField(max_length=150)
    category = models.CharField(max_length=30, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField()
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    notes = models.TextField(blank=True)
    receipt_image = models.ImageField(upload_to='expenses/', blank=True, null=True)

    class Meta:
        ordering = ['-expense_date']

    def __str__(self):
        return f"{self.title}: ₹{self.amount} ({self.expense_date})"

class CashRegister(TimeStampedModel):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='cash_registers')
    name = models.CharField(max_length=100, default='Main Counter')
    current_balance = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.shop.name} - {self.name} (₹{self.current_balance})"

class CashShift(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = 'OPEN', 'Shift Open'
        CLOSED = 'CLOSED', 'Shift Closed & Reconciled'

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='shifts')
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='cash_shifts')
    register = models.ForeignKey(CashRegister, on_delete=models.CASCADE, related_name='shifts', null=True, blank=True)
    
    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    opening_cash = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    cash_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    upi_sales = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cash_refunds = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    expected_closing_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    actual_closing_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    difference = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-start_time']

    def close_shift(self, actual_cash: float, notes: str = ''):
        self.actual_closing_cash = actual_cash
        self.expected_closing_cash = self.opening_cash + self.cash_sales - self.cash_refunds
        self.difference = self.actual_closing_cash - self.expected_closing_cash
        self.status = self.Status.CLOSED
        self.end_time = models.functions.Now()
        self.notes = notes
        self.save()

class DailySalesSummary(TimeStampedModel):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='daily_summaries')
    date = models.DateField(db_index=True)
    total_bills = models.PositiveIntegerField(default=0)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    cash_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    upi_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    net_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    class Meta:
        unique_together = ('shop', 'date')
        ordering = ['-date']

