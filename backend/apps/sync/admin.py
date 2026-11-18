from django.contrib import admin
from .models import Device, SyncEvent, SyncConflict

@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ('device_name', 'shop', 'device_uuid', 'app_version', 'last_sync_time')
    list_filter = ('shop',)
    search_fields = ('device_name', 'device_uuid')

@admin.register(SyncEvent)
class SyncEventAdmin(admin.ModelAdmin):
    list_display = ('id', 'device', 'shop', 'event_type', 'status', 'retry_count', 'created_at', 'processed_at')
    list_filter = ('status', 'event_type', 'shop', 'created_at')
    search_fields = ('device__device_name', 'error_message')

@admin.register(SyncConflict)
class SyncConflictAdmin(admin.ModelAdmin):
    list_display = ('sync_event', 'shop', 'conflict_type', 'resolution', 'resolved_by', 'resolved_at')
    list_filter = ('resolution', 'shop')
    search_fields = ('conflict_type', 'resolution_notes')

