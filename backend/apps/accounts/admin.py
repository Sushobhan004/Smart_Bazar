from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, CustomerProfile, CustomerConsent, OTPVerification, LoginSession

@admin.register(User)
class CustomUserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'phone_number', 'role', 'is_verified', 'is_staff', 'is_active')
    list_filter = ('role', 'is_verified', 'is_staff', 'is_active')
    search_fields = ('username', 'email', 'phone_number', 'first_name', 'last_name')
    ordering = ('-date_joined',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('Smart Bazaar Profile', {'fields': ('role', 'phone_number', 'is_verified', 'profile_image')}),
    )

@admin.register(CustomerProfile)
class CustomerProfileAdmin(admin.ModelAdmin):
    list_display = ('customer_code', 'full_name', 'phone_number', 'email', 'total_spent', 'reward_points', 'visit_count', 'created_at')
    list_filter = ('registered_at_shop', 'created_at')
    search_fields = ('customer_code', 'full_name', 'phone_number', 'email')
    readonly_fields = ('customer_code', 'total_spent', 'visit_count', 'reward_points', 'wallet_balance', 'created_at', 'updated_at')

@admin.register(CustomerConsent)
class CustomerConsentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'consent_type', 'granted', 'worker', 'ip_address', 'created_at')
    list_filter = ('consent_type', 'granted')
    search_fields = ('customer__full_name', 'customer__phone_number', 'worker__username')

@admin.register(OTPVerification)
class OTPVerificationAdmin(admin.ModelAdmin):
    list_display = ('email', 'purpose', 'attempts_count', 'is_used', 'is_expired', 'created_at', 'expires_at')
    list_filter = ('purpose', 'is_used', 'created_at')
    search_fields = ('email', 'phone_number')
    readonly_fields = ('otp_hash', 'created_at', 'expires_at', 'resend_available_at')

@admin.register(LoginSession)
class LoginSessionAdmin(admin.ModelAdmin):
    list_display = ('user', 'device_id', 'ip_address', 'created_at', 'expires_at')
    search_fields = ('user__username', 'user__email', 'device_id', 'ip_address')

