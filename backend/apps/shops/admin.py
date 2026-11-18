from django.contrib import admin
from .models import Shop, ShopMembership

class ShopMembershipInline(admin.TabularInline):
    model = ShopMembership
    extra = 1

@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ('code', 'name', 'category', 'owner', 'phone', 'city', 'status', 'created_at')
    list_filter = ('status', 'category', 'city', 'state')
    search_fields = ('code', 'name', 'phone', 'email', 'gstin', 'owner__username')
    inlines = [ShopMembershipInline]

@admin.register(ShopMembership)
class ShopMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'shop', 'role_in_shop', 'can_give_discount', 'can_process_return', 'can_modify_inventory')
    list_filter = ('role_in_shop', 'shop', 'can_give_discount', 'can_process_return')
    search_fields = ('user__username', 'user__email', 'shop__name', 'shop__code')

