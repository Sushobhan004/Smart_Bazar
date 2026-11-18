import uuid
from decimal import Decimal
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.conf import settings
from apps.core.models import TimeStampedModel

LOW_STOCK_THRESHOLD = 15

class Inventory(TimeStampedModel):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='inventories')
    product = models.OneToOneField('products.Product', on_delete=models.CASCADE, related_name='inventory')
    current_stock = models.DecimalField(max_digits=12, decimal_places=2, default=0.00, db_index=True)
    reorder_level = models.PositiveIntegerField(default=LOW_STOCK_THRESHOLD)
    last_restocked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Inventories'
        unique_together = ('shop', 'product')

    def __str__(self):
        return f"{self.product.name}: {self.current_stock} in stock"

    @property
    def is_low_stock(self):
        """Every product strictly below 15 units triggers low-stock alerts."""
        return self.current_stock < Decimal(str(LOW_STOCK_THRESHOLD))

    @property
    def is_out_of_stock(self):
        return self.current_stock <= 0

class StockTransaction(TimeStampedModel):
    class TxType(models.TextChoices):
        PURCHASE = 'PURCHASE', 'New Purchase Receipt'
        SALE = 'SALE', 'POS Sale Deduct'
        RETURN_IN = 'RETURN_IN', 'Customer Return (Restocked)'
        DAMAGE = 'DAMAGE', 'Damaged Stock'
        EXPIRED = 'EXPIRED', 'Expired Stock'
        ADJUSTMENT = 'ADJUSTMENT', 'Manual Physical Audit Correction'

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='stock_transactions')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stock_transactions')
    tx_type = models.CharField(max_length=20, choices=TxType.choices, db_index=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, help_text="Positive for addition, negative for deduction")
    balance_after = models.DecimalField(max_digits=12, decimal_places=2)
    reference_id = models.CharField(max_length=100, blank=True, db_index=True, help_text="Sale ID, Purchase ID or Adjustment ID")
    performed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.tx_type} | {self.product.name} | qty: {self.quantity} | bal: {self.balance_after}"

class StockBatch(TimeStampedModel):
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='batches')
    batch_number = models.CharField(max_length=100, db_index=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    purchase_date = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True, db_index=True)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    class Meta:
        ordering = ['expiry_date']

    def __str__(self):
        return f"Batch {self.batch_number} - {self.product.name} (Exp: {self.expiry_date})"

class StockAdjustment(TimeStampedModel):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='stock_adjustments')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='adjustments')
    adjusted_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    old_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()

    class Meta:
        ordering = ['-created_at']


class StockNotification(TimeStampedModel):
    """Automatic low-stock (< 15) notification surfaced on Shop Owner and Worker/Cashier dashboards."""
    class Severity(models.TextChoices):
        WARNING = 'WARNING', 'Low Stock (< 15)'
        CRITICAL = 'CRITICAL', 'Out of Stock (0)'

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='stock_notifications')
    product = models.ForeignKey('products.Product', on_delete=models.CASCADE, related_name='stock_notifications')
    inventory = models.ForeignKey(Inventory, on_delete=models.CASCADE, related_name='notifications')
    current_stock = models.DecimalField(max_digits=12, decimal_places=2)
    threshold = models.PositiveIntegerField(default=LOW_STOCK_THRESHOLD)
    severity = models.CharField(max_length=20, choices=Severity.choices, default=Severity.WARNING, db_index=True)
    title = models.CharField(max_length=200)
    message = models.TextField()
    is_resolved = models.BooleanField(default=False, db_index=True)
    acknowledged_by_owner = models.BooleanField(default=False)
    acknowledged_by_worker = models.BooleanField(default=False)

    class Meta:
        ordering = ['current_stock', '-updated_at']

    def __str__(self):
        return f"[{self.severity}] {self.product.name} ({self.current_stock} left)"


def sync_stock_notification(inventory: Inventory):
    """Create/update an active low-stock notification whenever stock < 15, or resolve it once >= 15."""
    stock_val = Decimal(str(inventory.current_stock))
    if stock_val < Decimal(str(LOW_STOCK_THRESHOLD)):
        severity = StockNotification.Severity.CRITICAL if stock_val <= 0 else StockNotification.Severity.WARNING
        qty_display = int(stock_val) if stock_val == int(stock_val) else float(stock_val)
        unit = inventory.product.unit or 'PCS'
        if stock_val <= 0:
            title = f"🚨 OUT OF STOCK: {inventory.product.name}"
            msg = f"{inventory.product.name} has 0 {unit} remaining. Immediate restock needed!"
        else:
            title = f"⚠️ Low Stock: {inventory.product.name}"
            msg = f"Only {qty_display} {unit} remaining in stock (below threshold of {LOW_STOCK_THRESHOLD}). Please restock."

        notif = StockNotification.objects.filter(
            inventory=inventory,
            is_resolved=False
        ).first()
        if notif:
            if notif.current_stock != stock_val:
                notif.acknowledged_by_owner = False
                notif.acknowledged_by_worker = False
            notif.current_stock = stock_val
            notif.severity = severity
            notif.title = title
            notif.message = msg
            notif.save()
        else:
            StockNotification.objects.create(
                shop=inventory.shop,
                product=inventory.product,
                inventory=inventory,
                current_stock=stock_val,
                threshold=LOW_STOCK_THRESHOLD,
                severity=severity,
                title=title,
                message=msg,
                is_resolved=False
            )
    else:
        StockNotification.objects.filter(inventory=inventory, is_resolved=False).update(is_resolved=True)


@receiver(post_save, sender=Inventory)
def on_inventory_saved(sender, instance, **kwargs):
    """Automatically generate or resolve low-stock notifications (< 15) after any inventory update."""
    sync_stock_notification(instance)


