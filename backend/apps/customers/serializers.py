from rest_framework import serializers
from apps.customers.models import CustomerShopAccount, Offer, OfferEligibility, OfferRedemption, RewardLedger, CustomerNotification

class OfferSerializer(serializers.ModelSerializer):
    class Meta:
        model = Offer
        fields = [
            'id', 'shop', 'title', 'description', 'code', 'calculation_method',
            'min_spend_required', 'discount_type', 'reward_value', 'max_discount',
            'valid_from', 'valid_until', 'is_active'
        ]

class OfferEligibilitySerializer(serializers.ModelSerializer):
    offer_title = serializers.ReadOnlyField(source='offer.title')
    offer_reward_value = serializers.ReadOnlyField(source='offer.reward_value')
    discount_type = serializers.ReadOnlyField(source='offer.discount_type')

    class Meta:
        model = OfferEligibility
        fields = [
            'id', 'offer', 'offer_title', 'offer_reward_value', 'discount_type',
            'voucher_code', 'is_redeemed', 'redeemed_at', 'created_at'
        ]

class RewardLedgerSerializer(serializers.ModelSerializer):
    class Meta:
        model = RewardLedger
        fields = ['id', 'action', 'points', 'balance_after', 'description', 'created_at']

class CustomerShopAccountSerializer(serializers.ModelSerializer):
    shop_name = serializers.ReadOnlyField(source='shop.name')

    class Meta:
        model = CustomerShopAccount
        fields = ['id', 'shop', 'shop_name', 'shop_total_spent', 'visit_count', 'last_visit']

class CustomerNotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomerNotification
        fields = ['id', 'title', 'message', 'notification_type', 'is_read', 'created_at']

