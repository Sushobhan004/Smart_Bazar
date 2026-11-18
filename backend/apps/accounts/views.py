import sys
import random
import uuid
import secrets
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.db import transaction, models
from django.contrib.auth import authenticate
from rest_framework import status, views, permissions
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

def is_dev_or_test():
    return settings.DEBUG or 'test' in sys.argv

from apps.accounts.models import User, CustomerProfile, OTPVerification, CustomerConsent, LoginSession
from apps.accounts.serializers import (
    UserSerializer, CustomerProfileSerializer, CustomerSearchResponseSerializer,
    SendOTPSerializer, VerifyOTPSerializer, StaffLoginSerializer,
    WorkerAssistedRegisterRequestSerializer
)
from apps.shops.models import Shop, ShopMembership
from apps.core.models import AuditLog

def get_tokens_for_user(user, shop=None):
    refresh = RefreshToken.for_user(user)
    refresh['role'] = user.role
    refresh['email'] = user.email
    refresh['username'] = user.username
    if shop:
        refresh['shop_id'] = str(shop.id)
        refresh['shop_name'] = shop.name
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }

class SendOTPView(views.APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = SendOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        purpose = serializer.validated_data.get('purpose', 'LOGIN')
        phone = serializer.validated_data.get('phone_number', '')

        # Cooldown check
        recent_otp = OTPVerification.objects.filter(
            email=email,
            is_used=False,
            resend_available_at__gt=timezone.now()
        ).first()

        if recent_otp:
            wait_seconds = int((recent_otp.resend_available_at - timezone.now()).total_seconds())
            return Response({
                'error': f'Please wait {wait_seconds} seconds before requesting a new OTP.'
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        # Invalidate old active OTPs
        OTPVerification.objects.filter(email=email, is_used=False).update(is_used=True)

        # Generate 6-digit cryptographically secure OTP
        raw_otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        otp_hash = OTPVerification.hash_otp(raw_otp)

        now = timezone.now()
        otp_record = OTPVerification.objects.create(
            email=email,
            phone_number=phone,
            otp_hash=otp_hash,
            purpose=purpose,
            expires_at=now + timedelta(minutes=5),
            resend_available_at=now + timedelta(seconds=60)
        )

        # Send official Smart Bazaar email
        subject = f'Your Smart Bazaar OTP: {raw_otp}' if settings.DEBUG else 'Your Smart Bazaar Verification Code'
        message = (
            f"Greetings from Smart Bazaar!\n\n"
            f"Your one-time verification code is: {raw_otp}\n\n"
            f"This code is valid for 5 minutes. Never share this code with anyone.\n"
            f"Smart Bazaar official email authentication.\n"
        )
        try:
            send_mail(
                subject=subject,
                message=message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False
            )
        except Exception as e:
            # Still record in test/debug if SMTP is mock/console
            pass

        response_data = {
            'message': 'OTP sent successfully to your Gmail address.',
            'email': email,
            'purpose': purpose,
            'expires_in_seconds': 300
        }
        # For development ease, include in debug mode if console backend
        if is_dev_or_test():
            response_data['dev_otp'] = raw_otp

        return Response(response_data, status=status.HTTP_200_OK)

class VerifyOTPView(views.APIView):
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data['email'].strip().lower()
        raw_otp = serializer.validated_data['otp'].strip()
        purpose = serializer.validated_data.get('purpose', 'LOGIN')
        full_name = serializer.validated_data.get('full_name', '')
        phone = serializer.validated_data.get('phone_number', '')
        shop_id = serializer.validated_data.get('shop_id')

        otp_record = OTPVerification.objects.filter(
            email=email,
            is_used=False
        ).order_by('-created_at').first()

        if not otp_record:
            return Response({'error': 'No active OTP request found for this email.'}, status=status.HTTP_400_BAD_REQUEST)

        if otp_record.is_expired:
            return Response({'error': 'OTP has expired. Please request a new code.'}, status=status.HTTP_400_BAD_REQUEST)

        if otp_record.attempts_count >= 5:
            otp_record.is_used = True
            otp_record.save()
            return Response({'error': 'Maximum verification attempts exceeded. Please request a new code.'}, status=status.HTTP_429_TOO_MANY_REQUESTS)

        if not otp_record.check_otp(raw_otp):
            otp_record.attempts_count += 1
            otp_record.save()
            remaining = 5 - otp_record.attempts_count
            return Response({'error': f'Incorrect OTP. {remaining} attempt(s) remaining.'}, status=status.HTTP_400_BAD_REQUEST)

        # OTP verified successfully
        otp_record.is_used = True
        otp_record.save()

        with transaction.atomic():
            user = User.objects.filter(email=email, role=User.Role.CUSTOMER).first()
            if not user:
                # Create customer user without password!
                username = f"cust_{email.split('@')[0]}_{secrets.randbelow(10000)}"
                user = User.objects.create(
                    username=username,
                    email=email,
                    phone_number=phone,
                    role=User.Role.CUSTOMER,
                    is_verified=True
                )
                user.set_unusable_password()
                user.save()

            customer_profile, created = CustomerProfile.objects.get_or_create(
                user=user,
                defaults={
                    'customer_code': f"SB-CUST-{secrets.randbelow(900000) + 100000}",
                    'full_name': full_name or email.split('@')[0].capitalize(),
                    'phone_number': phone or user.phone_number or '',
                    'email': email,
                }
            )
            if not customer_profile.email:
                customer_profile.email = email
                customer_profile.save()

        tokens = get_tokens_for_user(user)
        return Response({
            'message': 'OTP verified successfully.',
            'tokens': tokens,
            'user': UserSerializer(user).data,
            'customer_profile': CustomerProfileSerializer(customer_profile).data
        }, status=status.HTTP_200_OK)

class CustomerSearchView(views.APIView):
    """Worker searches for existing customer by phone number."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        phone = request.query_params.get('phone', '').strip()
        query = request.query_params.get('query', '').strip()

        if not phone and not query:
            return Response({'error': 'Please provide a mobile number or search query.'}, status=status.HTTP_400_BAD_REQUEST)

        qs = CustomerProfile.objects.all()
        if phone:
            # Clean phone
            cleaned_phone = ''.join(filter(str.isdigit, phone))
            qs = qs.filter(phone_number__endswith=cleaned_phone[-10:])
        elif query:
            qs = qs.filter(
                models.Q(phone_number__icontains=query) |
                models.Q(full_name__icontains=query) |
                models.Q(customer_code__iexact=query)
            )

        customer = qs.first()
        if not customer:
            return Response({'exists': False, 'message': 'Customer not found.'}, status=status.HTTP_200_OK)

        return Response({
            'exists': True,
            'customer': CustomerSearchResponseSerializer(customer).data
        }, status=status.HTTP_200_OK)

class WorkerAssistedRegisterView(views.APIView):
    """Worker initiates assisted registration for a new customer."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = WorkerAssistedRegisterRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        full_name = serializer.validated_data['full_name'].strip()
        phone = serializer.validated_data['phone_number'].strip()
        email = serializer.validated_data['email'].strip().lower()
        shop_id = serializer.validated_data.get('shop_id')
        consent_given = serializer.validated_data.get('consent_given', True)

        if not consent_given:
            return Response({'error': 'Customer consent is required for registration.'}, status=status.HTTP_400_BAD_REQUEST)

        # Check duplicate mobile
        cleaned_phone = ''.join(filter(str.isdigit, phone))
        existing_phone = CustomerProfile.objects.filter(phone_number__endswith=cleaned_phone[-10:]).first()
        if existing_phone:
            return Response({
                'error': f'A customer with mobile number {phone} is already registered as {existing_phone.full_name}.'
            }, status=status.HTTP_409_CONFLICT)

        # Check duplicate email
        existing_email = CustomerProfile.objects.filter(email__iexact=email).first()
        if existing_email:
            return Response({
                'error': f'A customer with Gmail address {email} is already registered.'
            }, status=status.HTTP_409_CONFLICT)

        # Invalidate old OTPs for this email
        OTPVerification.objects.filter(email=email, is_used=False).update(is_used=True)

        raw_otp = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        otp_hash = OTPVerification.hash_otp(raw_otp)

        now = timezone.now()
        OTPVerification.objects.create(
            email=email,
            phone_number=phone,
            otp_hash=otp_hash,
            purpose='REGISTRATION',
            expires_at=now + timedelta(minutes=5),
            resend_available_at=now + timedelta(seconds=60)
        )

        # Send official email OTP
        subject = f'Smart Bazaar Registration OTP: {raw_otp}' if settings.DEBUG else 'Smart Bazaar Registration Code'
        message = (
            f"Dear {full_name},\n\n"
            f"Welcome to Smart Bazaar!\n"
            f"Your one-time registration code is: {raw_otp}\n\n"
            f"Provide this code to the store cashier to complete your account setup.\n"
            f"This code will expire in 5 minutes.\n"
        )
        try:
            send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [email], fail_silently=False)
        except Exception:
            pass

        response_data = {
            'message': f'Registration OTP sent to {email}.',
            'full_name': full_name,
            'phone_number': phone,
            'email': email,
        }
        if is_dev_or_test():
            response_data['dev_otp'] = raw_otp

        return Response(response_data, status=status.HTTP_200_OK)

class StaffLoginView(views.APIView):
    """Login for Super Admin, Shop Owner, and Worker."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = StaffLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        username = serializer.validated_data['username'].strip()
        password = serializer.validated_data['password']

        # Allow login via username/unique worker ID, email, or phone number
        lookup_username = username
        if '@' in username:
            matched = User.objects.filter(email__iexact=username).first()
            if matched:
                lookup_username = matched.username
        elif username.isdigit() and len(username) >= 10:
            matched = User.objects.filter(phone_number=username).first()
            if matched:
                lookup_username = matched.username
        else:
            matched = User.objects.filter(username__iexact=username).first()
            if matched:
                lookup_username = matched.username

        user = authenticate(username=lookup_username, password=password)
        if not user:
            return Response({'error': 'Invalid username/worker ID or password.'}, status=status.HTTP_401_UNAUTHORIZED)

        if user.role == User.Role.CUSTOMER:
            return Response({'error': 'Customer accounts must use passwordless Gmail OTP.'}, status=status.HTTP_403_FORBIDDEN)

        # Retrieve active shop membership if worker or owner
        shop = None
        role_in_shop = None
        db_alias = 'default'
        db_name = 'SmartBazaar_Core'
        db_status = 'ACTIVE'

        if user.role == User.Role.SHOP_OWNER:
            shop = user.owned_shops.filter(status=Shop.Status.APPROVED).first() or user.owned_shops.first()
        elif user.role == User.Role.WORKER:
            membership = user.shop_memberships.filter(is_active=True, shop__status=Shop.Status.APPROVED).first() or user.shop_memberships.filter(is_active=True).first()
            if membership:
                shop = membership.shop
                role_in_shop = membership.role_in_shop

        if shop:
            from apps.core.database_provisioner import resolve_shop_db_alias_for_user, provision_shop_database
            from apps.shops.models import ShopDatabaseMapping
            db_alias = resolve_shop_db_alias_for_user(user, shop.code)
            mapping = getattr(shop, 'database_mapping', None) or ShopDatabaseMapping.objects.using('default').filter(shop=shop).first()
            if not mapping:
                try:
                    mapping = provision_shop_database(shop)
                except Exception:
                    pass
            db_name = mapping.database_name if mapping else f"SmartBazaar_Shop_{shop.code.split('-')[-1] if '-' in shop.code else '001'}"
            db_status = mapping.status if mapping else 'ACTIVE'
            
            # Secure server-side session assignment
            if hasattr(request, 'session'):
                request.session['shop_db'] = db_alias
                request.session['shop_id'] = str(shop.id)
                request.session['shop_code'] = shop.code

        tokens = get_tokens_for_user(user, shop)
        AuditLog.objects.create(
            user=user,
            shop=shop,
            action='STAFF_LOGIN',
            model_name='User',
            object_id=str(user.id),
            details={'role': user.role, 'username': user.username, 'db': db_name}
        )

        owner_user = shop.owner if (shop and shop.owner) else user
        owner_name = owner_user.get_full_name() or owner_user.first_name or owner_user.username if owner_user else 'Shop Owner'
        owner_phone = owner_user.phone_number if owner_user else (shop.phone if shop else 'N/A')

        return Response({
            'tokens': tokens,
            'user': UserSerializer(user).data,
            'role': user.role,
            'shop': {
                'id': str(shop.id) if shop else None,
                'name': shop.name if shop else None,
                'code': shop.code if shop else None,
                'address': shop.address if shop else 'Kolkata',
                'city': shop.city if shop else 'Kolkata',
                'phone': shop.phone if shop else owner_phone,
                'owner_name': owner_name,
                'owner_phone': owner_phone,
                'upi_vpa': shop.upi_vpa if shop else None,
                'database_name': db_name,
                'database_alias': db_alias,
                'db_status': db_status,
                'logo_url': shop.logo.url if (shop and shop.logo) else '',
                'settings': shop.settings if shop else {}
            } if shop else None,
            'role_in_shop': role_in_shop
        }, status=status.HTTP_200_OK)

class CustomerMeView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.user.role != User.Role.CUSTOMER:
            return Response({'error': 'User is not a customer.'}, status=status.HTTP_403_FORBIDDEN)
        
        profile = getattr(request.user, 'customer_profile', None)
        if not profile:
            return Response({'error': 'Customer profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        return Response({
            'user': UserSerializer(request.user).data,
            'profile': CustomerProfileSerializer(profile).data
        }, status=status.HTTP_200_OK)
