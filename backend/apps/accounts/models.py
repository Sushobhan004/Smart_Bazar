import uuid
import hashlib
from datetime import timedelta
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.utils import timezone
from apps.core.models import TimeStampedModel

class UserManager(BaseUserManager):
    def create_user(self, email=None, username=None, password=None, **extra_fields):
        if not email and not username:
            raise ValueError('Either email or username must be set')
        if email:
            email = self.normalize_email(email)
            if not username:
                username = email
        user = self.model(email=email, username=username, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, username=None, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.SUPER_ADMIN)
        if not password:
            raise ValueError('Superuser must have a password.')
        return self.create_user(email=email, username=username, password=password, **extra_fields)

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPER_ADMIN = 'SUPER_ADMIN', 'Super Admin'
        SHOP_OWNER = 'SHOP_OWNER', 'Shop Owner'
        WORKER = 'WORKER', 'Worker / Cashier'
        CUSTOMER = 'CUSTOMER', 'Customer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.CUSTOMER, db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True, db_index=True)
    is_verified = models.BooleanField(default=False)
    profile_image = models.ImageField(upload_to='profiles/', blank=True, null=True)

    objects = UserManager()

    class Meta:
        ordering = ['-date_joined']

    def is_super_admin(self):
        return self.role == self.Role.SUPER_ADMIN or self.is_superuser

    def is_shop_owner(self):
        return self.role == self.Role.SHOP_OWNER

    def is_worker(self):
        return self.role == self.Role.WORKER

    def is_customer(self):
        return self.role == self.Role.CUSTOMER

class CustomerProfile(TimeStampedModel):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='customer_profile')
    customer_code = models.CharField(max_length=32, unique=True, db_index=True)
    full_name = models.CharField(max_length=150)
    phone_number = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(max_length=255, db_index=True)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    visit_count = models.PositiveIntegerField(default=0)
    reward_points = models.PositiveIntegerField(default=0)
    wallet_balance = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    registered_at_shop = models.ForeignKey('shops.Shop', on_delete=models.SET_NULL, null=True, blank=True, related_name='registered_customers')
    created_by_worker = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='worker_registered_customers')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.full_name} ({self.phone_number})"

    @property
    def masked_phone(self):
        if self.phone_number and len(self.phone_number) >= 10:
            return f"{self.phone_number[:2]}******{self.phone_number[-2:]}"
        return self.phone_number or ""

    @property
    def masked_email(self):
        if self.email and '@' in self.email:
            parts = self.email.split('@')
            user_part = parts[0]
            masked_user = user_part[:2] + '***' if len(user_part) > 2 else user_part + '***'
            return f"{masked_user}@{parts[1]}"
        return self.email or ""

class CustomerConsent(TimeStampedModel):
    customer = models.ForeignKey(CustomerProfile, on_delete=models.CASCADE, related_name='consents')
    consent_type = models.CharField(max_length=100, default='REGISTRATION_ASSENT')
    granted = models.BooleanField(default=True)
    worker = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    notes = models.TextField(blank=True)

class OTPVerification(models.Model):
    PURPOSE_CHOICES = (
        ('LOGIN', 'Customer Login'),
        ('REGISTRATION', 'Worker-Assisted Registration'),
        ('OWNER_REGISTRATION', 'Shop Owner Registration'),
        ('EMPLOYEE_REGISTRATION', 'Employee Registration'),
        ('CUSTOMER_REGISTRATION', 'Customer Registration'),
    )
    STATUS_CHOICES = (
        ('PENDING', 'Pending Verification'),
        ('VERIFIED', 'Verified Successfully'),
        ('EXPIRED', 'Expired'),
        ('FAILED', 'Failed / Max Attempts Exceeded'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(db_index=True)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    otp_hash = models.CharField(max_length=128)
    purpose = models.CharField(max_length=40, choices=PURPOSE_CHOICES, default='LOGIN', db_index=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    attempts_count = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    shop_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    account_id = models.CharField(max_length=64, blank=True, null=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    resend_available_at = models.DateTimeField()

    class Meta:
        ordering = ['-created_at']

    @staticmethod
    def hash_otp(raw_otp: str) -> str:
        return hashlib.sha256(raw_otp.encode('utf-8')).hexdigest()

    def check_otp(self, raw_otp: str) -> bool:
        return self.otp_hash == self.hash_otp(raw_otp)

    @property
    def is_expired(self) -> bool:
        return timezone.now() > self.expires_at

# Reusable alias for Part 2 & Part 7 requirements
EmailVerificationRecord = OTPVerification

class EmailDeliveryLog(models.Model):
    STATUS_CHOICES = (
        ('SENT', 'Sent Successfully'),
        ('FAILED', 'Failed Delivery'),
        ('PENDING', 'Pending Delivery'),
    )
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    recipient = models.EmailField(db_index=True)
    subject = models.CharField(max_length=255)
    purpose = models.CharField(max_length=64, db_index=True)
    provider = models.CharField(max_length=32, default='GMAIL_API')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING', db_index=True)
    gmail_message_id = models.CharField(max_length=128, blank=True, null=True)
    error_message = models.TextField(blank=True, null=True)
    shop_id = models.CharField(max_length=64, blank=True, null=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.purpose} to {self.recipient} [{self.status}]"

class LoginSession(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='login_sessions')
    device_id = models.CharField(max_length=128, blank=True)
    token_jti = models.CharField(max_length=255, blank=True, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

