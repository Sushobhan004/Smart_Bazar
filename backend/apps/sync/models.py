import uuid
from django.db import models
from django.conf import settings
from apps.core.models import TimeStampedModel

class Device(TimeStampedModel):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='devices')
    device_uuid = models.CharField(max_length=128, unique=True, db_index=True)
    device_name = models.CharField(max_length=100)
    app_version = models.CharField(max_length=30)
    last_sync_time = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.device_name} ({self.shop.name})"

class SyncEvent(TimeStampedModel):
    class EventType(models.TextChoices):
        OFFLINE_SALE = 'OFFLINE_SALE', 'Offline POS Sale'
        CUSTOMER_CREATE = 'CUSTOMER_CREATE', 'Offline Customer Registration'
        STOCK_AUDIT = 'STOCK_AUDIT', 'Offline Stock Adjustment'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Processing'
        APPLIED = 'APPLIED', 'Applied Successfully'
        CONFLICT = 'CONFLICT', 'Conflict Detected'
        FAILED = 'FAILED', 'Processing Failed'

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='sync_events')
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='sync_events')
    event_type = models.CharField(max_length=30, choices=EventType.choices)
    payload = models.JSONField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    retry_count = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['created_at']

class SyncConflict(TimeStampedModel):
    class Resolution(models.TextChoices):
        UNRESOLVED = 'UNRESOLVED', 'Awaiting Resolution'
        AUTO_RESOLVED = 'AUTO_RESOLVED', 'Auto Resolved'
        MANUAL_OVERRIDE = 'MANUAL_OVERRIDE', 'Manager Override'
        REJECTED = 'REJECTED', 'Rejected'

    sync_event = models.ForeignKey(SyncEvent, on_delete=models.CASCADE, related_name='conflicts')
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='sync_conflicts')
    conflict_type = models.CharField(max_length=100)
    details = models.JSONField(default=dict)
    resolution = models.CharField(max_length=20, choices=Resolution.choices, default=Resolution.UNRESOLVED)
    resolved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)

