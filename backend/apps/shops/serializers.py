from rest_framework import serializers
from apps.shops.models import Shop, ShopMembership
from apps.accounts.serializers import UserSerializer

class ShopSerializer(serializers.ModelSerializer):
    owner_name = serializers.ReadOnlyField(source='owner.username')

    class Meta:
        model = Shop
        fields = [
            'id', 'owner', 'owner_name', 'name', 'code', 'category', 'description',
            'phone', 'email', 'address', 'city', 'state', 'pincode', 'gstin',
            'status', 'upi_vpa', 'upi_name', 'settings', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

class ShopMembershipSerializer(serializers.ModelSerializer):
    user_details = UserSerializer(source='user', read_only=True)
    shop_name = serializers.ReadOnlyField(source='shop.name')

    class Meta:
        model = ShopMembership
        fields = [
            'id', 'shop', 'shop_name', 'user', 'user_details', 'role_in_shop',
            'can_give_discount', 'max_discount_percent', 'can_process_return',
            'can_modify_inventory', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

