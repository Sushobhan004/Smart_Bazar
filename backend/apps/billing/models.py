import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel

class Sale(TimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH = 'CASH', 'Cash'
        UPI = 'UPI', 'UPI / PhonePe'
        CARD = 'CARD', 'Credit / Debit Card'
        WALLET = 'WALLET', 'Rewards Wallet'
        MIXED = 'MIXED', 'Split / Mixed'

    class PaymentStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Payment'
        COMPLETED = 'COMPLETED', 'Completed / Paid'
        CANCELLED = 'CANCELLED', 'Cancelled'
        REFUNDED = 'REFUNDED', 'Refunded'

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='sales')
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='worker_sales')
    customer = models.ForeignKey('accounts.CustomerProfile', on_delete=models.SET_NULL, null=True, blank=True, related_name='purchases')
    
    bill_number = models.CharField(max_length=50, db_index=True)
    is_guest = models.BooleanField(default=False)
    guest_name = models.CharField(max_length=100, blank=True)
    guest_phone = models.CharField(max_length=20, blank=True)
    
    # Financial breakdown
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    round_off = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    final_total = models.DecimalField(max_digits=12, decimal_places=2, db_index=True)
    
    payment_method = models.CharField(max_length=20, choices=PaymentMethod.choices, default=PaymentMethod.CASH)
    payment_status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.COMPLETED, db_index=True)
    
    idempotency_key = models.CharField(max_length=128, unique=True, db_index=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']
        unique_together = ('shop', 'bill_number')

    def __str__(self):
        return f"{self.bill_number} - ₹{self.final_total} ({self.shop.name})"

class SaleItem(TimeStampedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('products.Product', on_delete=models.PROTECT, related_name='sale_items')
    product_name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=100, blank=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    def __str__(self):
        return f"{self.product_name} x {self.quantity} = ₹{self.total_price}"

class Invoice(TimeStampedModel):
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=60, unique=True, db_index=True)
    pdf_file = models.FileField(upload_to='invoices/', blank=True, null=True)
    qr_data = models.TextField(blank=True, help_text="UPI intent or digital bill verification URL")
    sent_to_email = models.EmailField(blank=True, null=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"Invoice {self.invoice_number}"

class Payment(TimeStampedModel):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=Sale.PaymentMethod.choices)
    transaction_id = models.CharField(max_length=100, blank=True, db_index=True)
    gateway_ref = models.CharField(max_length=100, blank=True)
    is_success = models.BooleanField(default=True)
    metadata = models.JSONField(default=dict, blank=True)

class Return(TimeStampedModel):
    sale = models.ForeignKey(Sale, on_delete=models.PROTECT, related_name='returns')
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='returns')
    worker = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    return_number = models.CharField(max_length=50, unique=True)
    refund_amount = models.DecimalField(max_digits=12, decimal_places=2)
    refund_method = models.CharField(max_length=20, default='CASH')
    reason = models.TextField()

class ReturnItem(TimeStampedModel):
    return_record = models.ForeignKey(Return, on_delete=models.CASCADE, related_name='items')
    sale_item = models.ForeignKey(SaleItem, on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    refund_amount = models.DecimalField(max_digits=10, decimal_places=2)
    is_restocked = models.BooleanField(default=True)

