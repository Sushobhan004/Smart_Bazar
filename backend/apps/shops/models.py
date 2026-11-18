import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel

class Shop(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Approval'
        APPROVED = 'APPROVED', 'Approved & Active'
        SUSPENDED = 'SUSPENDED', 'Suspended'

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='owned_shops')
    name = models.CharField(max_length=200, db_index=True)
    code = models.CharField(max_length=32, unique=True, db_index=True)
    category = models.CharField(max_length=100, default='General Retail')
    description = models.TextField(blank=True)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100, default='West Bengal')
    pincode = models.CharField(max_length=10)
    gstin = models.CharField(max_length=20, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.APPROVED, db_index=True)
    
    # Fintech & Payment Config
    upi_vpa = models.CharField(max_length=100, blank=True, help_text="e.g. smartbazaar@okaxis")
    upi_name = models.CharField(max_length=100, blank=True)
    logo = models.ImageField(upload_to='shop_logos/', blank=True, null=True)
    
    # Configurable Policies
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"

class ShopMembership(TimeStampedModel):
    class RoleInShop(models.TextChoices):
        MANAGER = 'MANAGER', 'Store Manager'
        CASHIER = 'CASHIER', 'Cashier / Worker'
        STOCK_KEEPER = 'STOCK_KEEPER', 'Stock Keeper'

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name='memberships')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shop_memberships')
    role_in_shop = models.CharField(max_length=20, choices=RoleInShop.choices, default=RoleInShop.CASHIER)
    can_give_discount = models.BooleanField(default=False)
    max_discount_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    can_process_return = models.BooleanField(default=False)
    can_modify_inventory = models.BooleanField(default=False)

    class Meta:
        unique_together = ('shop', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} @ {self.shop.name} ({self.role_in_shop})"

class ShopDatabaseMapping(TimeStampedModel):
    class ProvisioningStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Provisioning'
        IN_PROGRESS = 'IN_PROGRESS', 'Provisioning In Progress'
        ACTIVE = 'ACTIVE', 'Active & Ready'
        FAILED = 'FAILED', 'Provisioning Failed'

    shop = models.OneToOneField(Shop, on_delete=models.CASCADE, related_name='database_mapping')
    shop_id_code = models.CharField(max_length=50, unique=True, db_index=True)  # e.g. SB-SHOP-001
    database_name = models.CharField(max_length=150, unique=True, db_index=True)  # e.g. SmartBazaar_Shop_001
    database_alias = models.CharField(max_length=100, unique=True, db_index=True)  # e.g. shop_001
    db_engine = models.CharField(max_length=50, default='sqlite3')  # sqlite3 or postgresql
    db_path = models.CharField(max_length=500, blank=True)
    db_host = models.CharField(max_length=200, blank=True)
    db_port = models.CharField(max_length=10, blank=True)
    db_user = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30, choices=ProvisioningStatus.choices, default=ProvisioningStatus.PENDING)
    last_migrated_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.shop_id_code} -> {self.database_name} ({self.status})"


