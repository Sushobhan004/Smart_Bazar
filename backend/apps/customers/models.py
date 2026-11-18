import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel

class CustomerShopAccount(TimeStampedModel):
    customer = models.ForeignKey('accounts.CustomerProfile', on_delete=models.CASCADE, related_name='shop_accounts')
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='customer_accounts')
    shop_total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    visit_count = models.PositiveIntegerField(default=0)
    last_visit = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('customer', 'shop')
        ordering = ['-shop_total_spent']

    def __str__(self):
        return f"{self.customer.full_name} @ {self.shop.name}: ₹{self.shop_total_spent}"

class Offer(TimeStampedModel):
    class DiscountType(models.TextChoices):
        FLAT = 'FLAT', 'Flat Amount (₹)'
        PERCENTAGE = 'PERCENTAGE', 'Percentage (%)'

    class CalculationMethod(models.TextChoices):
        SINGLE_BILL = 'SINGLE_BILL', 'Single Bill Threshold'
        MONTHLY_CUMULATIVE = 'MONTHLY_CUMULATIVE', 'Monthly Cumulative Spending'
        LIFETIME = 'LIFETIME', 'Lifetime Shop Spending'

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='offers', null=True, blank=True)
    title = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    code = models.CharField(max_length=50, unique=True, db_index=True)
    
    # Qualification Rules
    calculation_method = models.CharField(max_length=30, choices=CalculationMethod.choices, default=CalculationMethod.SINGLE_BILL)
    min_spend_required = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    
    # Reward Benefit
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices, default=DiscountType.FLAT)
    reward_value = models.DecimalField(max_digits=10, decimal_places=2, help_text="Voucher amount or % off")
    max_discount = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    
    valid_from = models.DateTimeField()
    valid_until = models.DateTimeField()
    max_total_usage = models.PositiveIntegerField(default=1000)
    times_used = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.code})"

class OfferEligibility(TimeStampedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='eligibilities')
    customer = models.ForeignKey('accounts.CustomerProfile', on_delete=models.CASCADE, related_name='offer_eligibilities')
    is_eligible = models.BooleanField(default=True)
    voucher_code = models.CharField(max_length=64, unique=True, db_index=True)
    is_redeemed = models.BooleanField(default=False)
    redeemed_at = models.DateTimeField(null=True, blank=True)

class OfferRedemption(TimeStampedModel):
    offer = models.ForeignKey(Offer, on_delete=models.CASCADE, related_name='redemptions')
    customer = models.ForeignKey('accounts.CustomerProfile', on_delete=models.CASCADE, related_name='redemptions')
    sale = models.ForeignKey('billing.Sale', on_delete=models.CASCADE, related_name='offer_redemptions')
    amount_saved = models.DecimalField(max_digits=10, decimal_places=2)

class RewardLedger(TimeStampedModel):
    class Action(models.TextChoices):
        EARNED = 'EARNED', 'Points Earned from Purchase'
        REDEEMED = 'REDEEMED', 'Points Redeemed on Bill'
        EXPIRED = 'EXPIRED', 'Points Expired'
        ADJUSTED = 'ADJUSTED', 'Manual Adjustment'

    customer = models.ForeignKey('accounts.CustomerProfile', on_delete=models.CASCADE, related_name='rewards_history')
    shop = models.ForeignKey('shops.Shop', on_delete=models.SET_NULL, null=True, blank=True)
    sale = models.ForeignKey('billing.Sale', on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=20, choices=Action.choices)
    points = models.IntegerField()
    balance_after = models.IntegerField()
    description = models.CharField(max_length=255)

    class Meta:
        ordering = ['-created_at']

class CustomerNotification(TimeStampedModel):
    customer = models.ForeignKey('accounts.CustomerProfile', on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=150)
    message = models.TextField()
    notification_type = models.CharField(max_length=50, default='SYSTEM')
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

