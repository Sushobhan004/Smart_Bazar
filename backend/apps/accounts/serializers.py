import random
import string
from rest_framework import serializers
from django.contrib.auth import authenticate
from apps.accounts.models import User, CustomerProfile, OTPVerification, CustomerConsent, LoginSession
from apps.shops.models import Shop, ShopMembership

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'phone_number', 'role', 'is_verified', 'first_name', 'last_name']
        read_only_fields = ['id', 'is_verified']

class CustomerProfileSerializer(serializers.ModelSerializer):
    masked_phone = serializers.ReadOnlyField()
    masked_email = serializers.ReadOnlyField()
    
    class Meta:
        model = CustomerProfile
        fields = [
            'id', 'customer_code', 'full_name', 'phone_number', 'email',
            'masked_phone', 'masked_email', 'total_spent', 'visit_count',
            'reward_points', 'wallet_balance', 'registered_at_shop', 'created_at'
        ]
        read_only_fields = ['id', 'customer_code', 'total_spent', 'visit_count', 'reward_points', 'wallet_balance', 'created_at']

class CustomerSearchResponseSerializer(serializers.ModelSerializer):
    masked_phone = serializers.ReadOnlyField()
    masked_email = serializers.ReadOnlyField()
    shop_code = serializers.SerializerMethodField()
    shop_name = serializers.SerializerMethodField()
    registered_by = serializers.SerializerMethodField()

    class Meta:
        model = CustomerProfile
        fields = [
            'id', 'customer_code', 'full_name', 'phone_number', 'email',
            'masked_phone', 'masked_email', 'total_spent', 'visit_count',
            'reward_points', 'shop_code', 'shop_name', 'registered_by'
        ]

    def get_shop_code(self, obj):
        return obj.registered_at_shop.code if obj.registered_at_shop else ''

    def get_shop_name(self, obj):
        return obj.registered_at_shop.name if obj.registered_at_shop else ''

    def get_registered_by(self, obj):
        if obj.created_by_worker:
            return obj.created_by_worker.get_full_name() or obj.created_by_worker.username
        return ''

class SendOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    purpose = serializers.ChoiceField(choices=['LOGIN', 'REGISTRATION'], default='LOGIN')
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)

class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField()
    otp = serializers.CharField(max_length=6, min_length=6)
    purpose = serializers.ChoiceField(choices=['LOGIN', 'REGISTRATION'], default='LOGIN')
    # If registration:
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    phone_number = serializers.CharField(max_length=20, required=False, allow_blank=True)
    shop_id = serializers.UUIDField(required=False, allow_null=True)

class StaffLoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

class WorkerAssistedRegisterRequestSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150)
    phone_number = serializers.CharField(max_length=20)
    email = serializers.EmailField()
    shop_id = serializers.UUIDField(required=False, allow_null=True)
    consent_given = serializers.BooleanField(default=True)

