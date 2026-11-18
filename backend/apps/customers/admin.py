from django.contrib import admin
from .models import CustomerShopAccount, Offer, OfferEligibility, OfferRedemption, RewardLedger, CustomerNotification

@admin.register(CustomerShopAccount)
class CustomerShopAccountAdmin(admin.ModelAdmin):
    list_display = ('customer', 'shop', 'shop_total_spent', 'visit_count', 'last_visit')
    list_filter = ('shop',)
    search_fields = ('customer__full_name', 'customer__phone_number', 'shop__name')

@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ('title', 'code', 'shop', 'calculation_method', 'min_spend_required', 'discount_type', 'reward_value', 'valid_until', 'times_used')
    list_filter = ('calculation_method', 'discount_type', 'shop')
    search_fields = ('title', 'code', 'description')

@admin.register(OfferEligibility)
class OfferEligibilityAdmin(admin.ModelAdmin):
    list_display = ('offer', 'customer', 'voucher_code', 'is_eligible', 'is_redeemed', 'redeemed_at')
    list_filter = ('is_eligible', 'is_redeemed')
    search_fields = ('voucher_code', 'customer__full_name', 'offer__code')

@admin.register(OfferRedemption)
class OfferRedemptionAdmin(admin.ModelAdmin):
    list_display = ('offer', 'customer', 'sale', 'amount_saved', 'created_at')
    search_fields = ('customer__full_name', 'sale__bill_number', 'offer__code')

@admin.register(RewardLedger)
class RewardLedgerAdmin(admin.ModelAdmin):
    list_display = ('customer', 'action', 'points', 'balance_after', 'shop', 'created_at')
    list_filter = ('action', 'shop')
    search_fields = ('customer__full_name', 'description')

@admin.register(CustomerNotification)
class CustomerNotificationAdmin(admin.ModelAdmin):
    list_display = ('customer', 'title', 'notification_type', 'is_read', 'created_at')
    list_filter = ('is_read', 'notification_type')
    search_fields = ('customer__full_name', 'title', 'message')

