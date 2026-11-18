# -*- coding: utf-8 -*-
"""
Smart Bazaar — Hierarchical Email Verification and Automated Account Provisioning Endpoints
Workflows:
1. Super Admin -> Verify Shop Owner Gmail -> Create Owner & Provision DB -> Send Activation Email
2. Shop Owner -> Verify Employee Gmail -> Create Staff in Tenant DB -> Send Staff Welcome Email
3. Staff Member -> Verify Customer Gmail -> Save Active Customer in Tenant DB
4. Email Service -> Gmail API Connectivity Test
"""

import re
import json
import uuid
import secrets
import logging
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import models, transaction, connections
from django.utils import timezone

from apps.accounts.models import User, CustomerProfile, OTPVerification, EmailDeliveryLog
from apps.accounts.otp_service import OTPService
from apps.core.email_service import EmailService
from apps.shops.models import Shop, ShopMembership, ShopDatabaseMapping
from apps.core.database_provisioner import provision_shop_database, get_shop_db_alias, get_shop_db_name
from apps.core.models import AuditLog

logger = logging.getLogger('smart_bazaar.workflows')

def _is_valid_uuid(val):
    if not val:
        return False
    try:
        uuid.UUID(str(val).strip())
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def _parse_body(request):
    """Safely extracts JSON payload from request, falling back to request.POST."""
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode('utf-8'))
        except Exception:
            pass
    if not payload and request.POST:
        payload = request.POST.dict()
    return payload


# =========================================================================
# WORKFLOW 1: SUPER ADMIN CREATES SHOP OWNER
# =========================================================================

@csrf_exempt
def api_superadmin_owners_send_otp(request):
    """
    POST /api/super-admin/owners/send-otp
    POST /api/superadmin/owners/send-otp/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    name = (data.get('full_name') or data.get('name') or data.get('owner_name') or data.get('ownerFullName') or '').strip()
    shop_name = (data.get('shop_name') or data.get('shopName') or data.get('store_name') or 'Smart Bazaar Superstore').strip()
    phone = (data.get('phone_number') or data.get('phone') or data.get('ownerPhone') or '').strip()
    email = (data.get('email') or data.get('ownerGmail') or data.get('gmail') or '').strip().lower()
    username = (data.get('username') or data.get('ownerUsername') or data.get('login_id') or '').strip()
    shop_address = (data.get('shop_address') or data.get('address') or data.get('ownerShopAddress') or data.get('ownerAddress') or '').strip()

    if not name:
        return JsonResponse({'error': 'Owner full name is required.'}, status=400)
    if not phone or not re.match(r'^\d{10}$', phone):
        return JsonResponse({'error': 'A valid 10-digit mobile number is required.'}, status=400)
    if not email or '@' not in email:
        return JsonResponse({'error': 'A valid owner Gmail address is required.'}, status=400)
    if not username:
        return JsonResponse({'error': 'Owner Login ID / Username is required.'}, status=400)

    # Check whether Gmail address is already registered
    if User.objects.filter(email=email).exists():
        return JsonResponse({'error': f"The Gmail address '{email}' is already registered with another account."}, status=400)

    # Check whether Owner Login ID is available
    if User.objects.filter(username=username).exists():
        return JsonResponse({'error': f"Owner Login ID '{username}' is already in use. Please choose another."}, status=400)

    # Metadata saved in pending verification session
    metadata = {
        'full_name': name,
        'shop_name': shop_name,
        'phone_number': phone,
        'username': username,
        'shop_address': shop_address,
        'password': data.get('password', '').strip(),
        'shop_code': data.get('shop_code', '').strip()
    }

    res = OTPService.generate_and_send_otp(
        email=email,
        purpose='OWNER_REGISTRATION',
        recipient_name=name,
        phone_number=phone,
        metadata=metadata
    )

    if not res.get('success'):
        status_code = 429 if res.get('status') == 'COOLDOWN' else 400
        return JsonResponse(res, status=status_code)

    return JsonResponse(res)


@csrf_exempt
def api_superadmin_owners_verify_otp(request):
    """
    POST /api/super-admin/owners/verify-otp
    POST /api/superadmin/owners/verify-otp/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    raw_otp = data.get('otp', '').strip()
    verification_id = data.get('verification_id', '').strip()
    email = data.get('email', '').strip().lower()

    if not raw_otp:
        return JsonResponse({'error': 'Verification code cannot be empty.'}, status=400)

    res = OTPService.verify_otp(
        raw_otp=raw_otp,
        purpose='OWNER_REGISTRATION',
        verification_id=verification_id or None,
        email=email or None
    )

    if not res.get('success'):
        return JsonResponse(res, status=400)

    return JsonResponse(res)


@csrf_exempt
def api_superadmin_owners_create(request):
    """
    POST /api/super-admin/owners/create
    POST /api/superadmin/owners/create/
    Enforces backend OTP verification before provisioning dedicated DB and creating Owner.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    email = (data.get('email') or data.get('ownerGmail') or data.get('gmail') or '').strip().lower()
    verification_id = (data.get('verification_id') or data.get('verificationId') or '').strip()
    otp = data.get('otp', '').strip()

    name = (data.get('full_name') or data.get('name') or data.get('owner_name') or data.get('ownerFullName') or '').strip()
    shop_name = (data.get('shop_name') or data.get('shopName') or data.get('store_name') or 'Smart Bazaar Superstore').strip()
    phone = (data.get('phone_number') or data.get('phone') or data.get('ownerPhone') or '').strip()
    username = (data.get('username') or data.get('ownerUsername') or data.get('login_id') or '').strip()
    password = data.get('password', '').strip() or 'OwnerPass@123'
    address = (data.get('shop_address') or data.get('address') or data.get('ownerShopAddress') or data.get('ownerAddress') or 'Kolkata, WB').strip()

    # STRICT BACKEND VERIFICATION CHECK:
    # 1. If verification_id is supplied, check that it is already in VERIFIED state
    is_verified = False
    if verification_id:
        record = OTPVerification.objects.filter(id=verification_id, purpose='OWNER_REGISTRATION', status='VERIFIED').first()
        if record:
            is_verified = True
            # Hydrate missing fields from metadata if omitted
            meta = record.metadata or {}
            name = name or meta.get('full_name')
            phone = phone or meta.get('phone_number')
            username = username or meta.get('username')
            shop_name = shop_name or meta.get('shop_name')
            address = address or meta.get('shop_address')
            password = password or meta.get('password')

    # 2. If otp is supplied directly in payload, perform verification on the spot
    if not is_verified and otp:
        verify_res = OTPService.verify_otp(
            raw_otp=otp,
            purpose='OWNER_REGISTRATION',
            verification_id=verification_id or None,
            email=email or None
        )
        if verify_res.get('success'):
            is_verified = True
        else:
            return JsonResponse({'error': f"Verification failed: {verify_res.get('error')}"}, status=400)

    if not is_verified:
        return JsonResponse({
            'error': 'Account creation denied: You must verify the Shop Owner Gmail address with OTP before creating the store.'
        }, status=403)

    # Check uniqueness again inside transaction boundary
    if User.objects.filter(email=email).exists():
        return JsonResponse({'error': f"The Gmail address '{email}' is already registered."}, status=400)
    if User.objects.filter(username=username).exists():
        return JsonResponse({'error': f"Owner Login ID '{username}' is already in use."}, status=400)

    try:
        with transaction.atomic(using='default'):
            # 1. Create central Shop Owner user
            name_parts = (name or '').strip().split(' ', 1)
            f_name = name_parts[0] if name_parts else 'Shop'
            l_name = name_parts[1] if len(name_parts) > 1 else 'Owner'
            owner_user = User.objects.db_manager('default').create_user(
                username=username,
                email=email,
                password=password,
                role=User.Role.SHOP_OWNER,
                phone_number=phone,
                first_name=f_name,
                last_name=l_name,
                is_active=True
            )

            # 2. Generate unique Shop ID and Owner ID
            count = Shop.objects.using('default').count() + 1
            shop_code = data.get('shop_code', '').strip() or f"SB-SHOP-{count:03d}"
            owner_id = f"SB-OWNER-{count:03d}"

            # Ensure unique code
            while Shop.objects.using('default').filter(code=shop_code).exists():
                count += 1
                shop_code = f"SB-SHOP-{count:03d}"

            # 3. Create Shop Record in Central DB
            shop = Shop.objects.using('default').create(
                name=shop_name,
                code=shop_code,
                owner=owner_user,
                address=address,
                city='Kolkata',
                phone=phone,
                email=email,
                is_active=True
            )

            # 4. Create Owner Membership
            ShopMembership.objects.using('default').create(
                user=owner_user,
                shop=shop,
                role_in_shop='MANAGER',
                is_active=True
            )

            # 5. Provision Dedicated Independent Database & Apply Schema Migrations
            provision_shop_database(shop)

            # 6. Dispatch Official Account Activation Email via Gmail API
            host = request.get_host()
            scheme = 'https' if request.is_secure() else 'http'
            login_url = f"{scheme}://{host}/"

            email_res = EmailService.sendAccountActivationEmail(
                email=email,
                owner_name=name,
                shop_name=shop_name,
                owner_id=owner_id,
                shop_id=shop_code,
                login_id=username,
                temp_password=password,
                login_url=login_url
            )

            # 7. Audit Log
            AuditLog.objects.using('default').create(
                user=owner_user,
                shop=shop,
                action='CREATE_SHOP_OWNER',
                model_name='Shop',
                object_id=str(shop.id),
                details={
                    'shop_code': shop_code,
                    'owner_id': owner_id,
                    'email': email,
                    'gmail_sent': email_res.get('success', False)
                }
            )

        logger.info(f"✓ Created Shop Owner {username} ({owner_id}) for store {shop_code} with dedicated DB.")
        return JsonResponse({
            'success': True,
            'message': f"Shop Owner '{name}' registered and dedicated database provisioned successfully.",
            'shop_id': shop_code,
            'owner_id': owner_id,
            'login_id': username,
            'owner_name': name,
            'shop_name': shop_name,
            'email': email,
            'email_delivery': email_res
        })

    except Exception as ex:
        logger.error(f"Failed to provision Shop Owner: {ex}", exc_info=True)
        return JsonResponse({'error': f"Failed to provision store and database: {str(ex)}"}, status=500)


# =========================================================================
# WORKFLOW 2: SHOP OWNER CREATES EMPLOYEE / WORKER
# =========================================================================

@csrf_exempt
def api_shop_employees_send_otp(request):
    """
    POST /api/shop/employees/send-otp
    POST /api/admin/workers/send-otp/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    name = (data.get('full_name') or data.get('name') or data.get('worker_name') or data.get('employee_name') or '').strip()
    phone = (data.get('phone_number') or data.get('phone') or '').strip()
    email = (data.get('email') or data.get('gmail') or '').strip().lower()
    role_in_shop = (data.get('role_in_shop') or data.get('role') or '').strip() or 'CASHIER'
    username = (data.get('username') or data.get('worker_id') or data.get('employee_id') or data.get('login_id') or '').strip()
    shop_id = (data.get('shop_id') or data.get('shop_code') or '').strip()

    if not name:
        return JsonResponse({'error': 'Employee full name is required.'}, status=400)
    if not phone or not re.match(r'^\d{10}$', phone):
        return JsonResponse({'error': 'A valid 10-digit mobile number is required.'}, status=400)
    if not email or '@' not in email:
        return JsonResponse({'error': 'A valid employee Gmail address is required.'}, status=400)

    if not username:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
        username = f"cashier_{clean_name[:10]}" if clean_name else f"worker_{phone[-4:] if len(phone) >= 4 else '01'}"

    # Check whether employee login ID is available
    if User.objects.using('default').filter(username=username).exists():
        return JsonResponse({'error': f"Employee Login ID '{username}' is already in use. Please select another."}, status=400)

    metadata = {
        'full_name': name,
        'phone_number': phone,
        'role_in_shop': role_in_shop,
        'username': username,
        'password': data.get('password', '').strip(),
        'shop_id': shop_id
    }

    res = OTPService.generate_and_send_otp(
        email=email,
        purpose='EMPLOYEE_REGISTRATION',
        recipient_name=name,
        phone_number=phone,
        shop_id=shop_id,
        metadata=metadata
    )

    if not res.get('success'):
        status_code = 429 if res.get('status') == 'COOLDOWN' else 400
        return JsonResponse(res, status=status_code)

    return JsonResponse(res)


@csrf_exempt
def api_shop_employees_verify_otp(request):
    """
    POST /api/shop/employees/verify-otp
    POST /api/admin/workers/verify-otp/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    raw_otp = data.get('otp', '').strip()
    verification_id = data.get('verification_id', '').strip()
    email = data.get('email', '').strip().lower()
    shop_id = data.get('shop_id', '').strip()

    if not raw_otp:
        return JsonResponse({'error': 'Verification code cannot be empty.'}, status=400)

    res = OTPService.verify_otp(
        raw_otp=raw_otp,
        purpose='EMPLOYEE_REGISTRATION',
        verification_id=verification_id or None,
        email=email or None,
        shop_id=shop_id or None
    )

    if not res.get('success'):
        return JsonResponse(res, status=400)

    return JsonResponse(res)


@csrf_exempt
def api_shop_employees_create(request):
    """
    POST /api/shop/employees/create
    POST /api/admin/workers/create/
    Enforces backend OTP verification before creating worker credentials and sending login email.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    email = (data.get('email') or data.get('gmail') or '').strip().lower()
    verification_id = data.get('verification_id', '').strip()
    otp = data.get('otp', '').strip()
    shop_id = (data.get('shop_id') or data.get('shop_code') or '').strip()

    name = (data.get('full_name') or data.get('name') or data.get('worker_name') or data.get('employee_name') or '').strip()
    phone = (data.get('phone_number') or data.get('phone') or '').strip()
    role_in_shop = (data.get('role_in_shop') or data.get('role') or '').strip() or 'CASHIER'
    username = (data.get('username') or data.get('worker_id') or data.get('employee_id') or data.get('login_id') or '').strip()
    password = data.get('password', '').strip() or 'WorkerPass@123'

    # STRICT BACKEND VERIFICATION CHECK:
    is_verified = False
    record = None
    if verification_id and _is_valid_uuid(verification_id):
        record = OTPVerification.objects.using('default').filter(id=verification_id, purpose='EMPLOYEE_REGISTRATION', status='VERIFIED').first()
    if not record and email:
        record = OTPVerification.objects.using('default').filter(email=email, purpose='EMPLOYEE_REGISTRATION', status='VERIFIED').order_by('-created_at').first()
        if record and (timezone.now() - record.created_at).total_seconds() > 900:
            record = None
    if not record and phone:
        record = OTPVerification.objects.using('default').filter(phone_number=phone, purpose='EMPLOYEE_REGISTRATION', status='VERIFIED').order_by('-created_at').first()
        if record and (timezone.now() - record.created_at).total_seconds() > 900:
            record = None

    if record:
        is_verified = True
        meta = record.metadata or {}
        name = name or meta.get('full_name') or meta.get('name')
        phone = phone or meta.get('phone_number') or meta.get('phone')
        username = username or meta.get('username') or meta.get('worker_id')
        role_in_shop = role_in_shop or meta.get('role_in_shop')
        password = password or meta.get('password')
        shop_id = shop_id or meta.get('shop_id') or meta.get('shop_code')

    if not is_verified and otp:
        verify_res = OTPService.verify_otp(
            raw_otp=otp,
            purpose='EMPLOYEE_REGISTRATION',
            verification_id=verification_id or None,
            email=email or None,
            shop_id=shop_id or None,
            phone_number=phone or None
        )
        if verify_res.get('success'):
            is_verified = True
        else:
            return JsonResponse({'error': f"Verification failed: {verify_res.get('error')}"}, status=400)

    if not is_verified:
        return JsonResponse({
            'error': 'Staff creation denied: You must verify the employee Gmail address with OTP before creating the account.'
        }, status=403)

    if not username:
        clean_name = re.sub(r'[^a-zA-Z0-9]', '', name.lower())
        username = f"cashier_{clean_name[:10]}" if clean_name else f"worker_{phone[-4:] if len(phone) >= 4 else '01'}"

    if User.objects.using('default').filter(username=username).exists():
        return JsonResponse({'error': f"Employee Login ID '{username}' is already in use."}, status=400)

    # Determine associated shop
    shop = None
    if shop_id:
        shop = Shop.objects.using('default').filter(code=shop_id).first() or Shop.objects.using('default').filter(id=shop_id).first()
    if not shop:
        shop = Shop.objects.using('default').first()

    try:
        with transaction.atomic(using='default'):
            emp_count = User.objects.using('default').filter(role='WORKER').count() + 1
            employee_id = (data.get('employee_id') or data.get('worker_id') or '').strip() or f"SB-EMP-{emp_count:03d}"

            emp_parts = (name or '').strip().split(' ', 1)
            emp_first = emp_parts[0] if emp_parts else 'Store'
            emp_last = emp_parts[1] if len(emp_parts) > 1 else 'Staff'
            worker = User.objects.db_manager('default').create_user(
                username=username,
                email=email,
                password=password,
                role=User.Role.WORKER,
                phone_number=phone,
                first_name=emp_first,
                last_name=emp_last,
                is_active=True
            )

            if shop:
                ShopMembership.objects.using('default').create(
                    user=worker,
                    shop=shop,
                    role_in_shop=role_in_shop,
                    is_active=True
                )

            # Sync worker into shop's dedicated tenant database if connected
            if shop:
                try:
                    tenant_alias = get_shop_db_alias(shop.code)
                    if tenant_alias in connections:
                        User.objects.using(tenant_alias).update_or_create(
                            id=worker.id,
                            defaults={
                                'username': worker.username,
                                'email': worker.email,
                                'role': worker.role,
                                'phone_number': worker.phone_number,
                                'first_name': worker.first_name,
                                'last_name': worker.last_name,
                                'is_active': worker.is_active
                            }
                        )
                except Exception as sync_err:
                    logger.warning(f"Note: Could not mirror worker {username} to tenant db: {sync_err}")

            # Send Employee Welcome Email via Gmail API
            host = request.get_host()
            scheme = 'https' if request.is_secure() else 'http'
            login_url = f"{scheme}://{host}/"

            email_res = EmailService.sendEmployeeWelcomeEmail(
                email=email,
                employee_name=name,
                shop_name=shop.name if shop else "Smart Bazaar",
                employee_id=employee_id,
                login_id=username,
                role=role_in_shop,
                temp_password=password,
                login_url=login_url,
                shop_id=shop.code if shop else "STORE"
            )

            AuditLog.objects.using('default').create(
                user=worker,
                shop=shop,
                action='CREATE_EMPLOYEE',
                model_name='User',
                object_id=str(worker.id),
                details={
                    'employee_id': employee_id,
                    'username': username,
                    'email': email,
                    'role_in_shop': role_in_shop,
                    'gmail_sent': email_res.get('success', False)
                }
            )

        logger.info(f"✓ Created Employee {username} ({employee_id}) for shop {shop.code if shop else 'N/A'}")
        return JsonResponse({
            'success': True,
            'message': f"Staff member '{name}' created successfully.",
            'employee_id': employee_id,
            'username': username,
            'name': name,
            'role': role_in_shop,
            'email': email,
            'email_delivery': email_res
        })

    except Exception as ex:
        logger.error(f"Failed to create employee: {ex}", exc_info=True)
        return JsonResponse({'error': f"Failed to create employee account: {str(ex)}"}, status=500)


# =========================================================================
# WORKFLOW 3: STAFF REGISTERS CUSTOMER
# =========================================================================

@csrf_exempt
def api_shop_customers_send_otp(request):
    """
    POST /api/shop/customers/send-otp
    POST /api/customers/send-otp/
    POST /api/pos/customers/send-otp/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    name = (data.get('full_name') or data.get('name') or '').strip()
    phone = (data.get('phone_number') or data.get('phone') or '').strip()
    email = (data.get('email') or data.get('gmail') or '').strip().lower()
    raw_shop = data.get('shop_id') or data.get('shop_code') or ''
    shop_id = str(raw_shop).strip() if raw_shop else ''

    if not phone or not re.match(r'^\d{10}$', phone):
        return JsonResponse({'error': 'A valid 10-digit customer mobile number is required.'}, status=400)
    if not email or '@' not in email:
        return JsonResponse({'error': 'A valid customer Gmail address is required for digital receipts.'}, status=400)

    # Check if customer already registered with this phone in central database
    shop = (Shop.objects.using('default').filter(code=shop_id).first() or Shop.objects.using('default').filter(id=shop_id).first()) if shop_id else Shop.objects.using('default').first()
    if CustomerProfile.objects.using('default').filter(phone_number=phone).exists():
        existing = CustomerProfile.objects.using('default').filter(phone_number=phone).first()
        return JsonResponse({
            'error': f"Customer with phone number {phone} is already registered as '{existing.full_name}'.",
            'is_existing': True,
            'customer_id': str(existing.id)
        }, status=400)

    metadata = {
        'full_name': name or 'Customer',
        'phone_number': phone,
        'email': email,
        'address': (data.get('address') or '').strip(),
        'shop_name': shop.name if shop else "Smart Bazaar",
        'shop_id': shop.code if shop else None
    }

    res = OTPService.generate_and_send_otp(
        email=email,
        purpose='CUSTOMER_REGISTRATION',
        recipient_name=name or 'Valued Customer',
        phone_number=phone,
        shop_id=shop.code if shop else None,
        metadata=metadata
    )

    if not res.get('success'):
        status_code = 429 if res.get('status') == 'COOLDOWN' else 400
        return JsonResponse(res, status=status_code)

    return JsonResponse(res)


@csrf_exempt
def api_shop_customers_verify_otp(request):
    """
    POST /api/shop/customers/verify-otp
    POST /api/customers/verify-otp/
    POST /api/pos/customers/verify-otp/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    raw_otp = (data.get('otp') or '').strip()
    verification_id = (data.get('verification_id') or '').strip()
    email = (data.get('email') or data.get('gmail') or '').strip().lower()
    raw_shop = data.get('shop_id') or data.get('shop_code') or ''
    shop_id = str(raw_shop).strip() if raw_shop else ''

    if not raw_otp:
        return JsonResponse({'error': 'Verification code cannot be empty.'}, status=400)

    res = OTPService.verify_otp(
        raw_otp=raw_otp,
        purpose='CUSTOMER_REGISTRATION',
        verification_id=verification_id or None,
        email=email or None,
        shop_id=shop_id or None
    )

    if not res.get('success'):
        return JsonResponse(res, status=400)

    return JsonResponse(res)


@csrf_exempt
def api_shop_customers_create(request):
    """
    POST /api/shop/customers/create
    POST /api/customers/register/
    POST /api/pos/customers/create/
    Enforces backend OTP verification before saving active customer record into current shop DB.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    try:
        data = _parse_body(request)
        email = (data.get('email') or data.get('gmail') or '').strip().lower()
        verification_id = (data.get('verification_id') or '').strip()
        otp = (data.get('otp') or '').strip()
        raw_shop = data.get('shop_id') or data.get('shop_code') or ''
        shop_id = str(raw_shop).strip() if raw_shop else ''

        name = (data.get('full_name') or data.get('name') or '').strip()
        phone = (data.get('phone_number') or data.get('phone') or '').strip()
        address = (data.get('address') or '').strip()

        # STRICT BACKEND VERIFICATION CHECK:
        is_verified = False
        record = None
        if verification_id and _is_valid_uuid(verification_id):
            record = OTPVerification.objects.using('default').filter(id=verification_id, purpose='CUSTOMER_REGISTRATION', status='VERIFIED').first()
        if not record and email:
            record = OTPVerification.objects.using('default').filter(email=email, purpose='CUSTOMER_REGISTRATION', status='VERIFIED').order_by('-created_at').first()
            if record and (timezone.now() - record.created_at).total_seconds() > 900:
                record = None
        if not record and phone:
            record = OTPVerification.objects.using('default').filter(phone_number=phone, purpose='CUSTOMER_REGISTRATION', status='VERIFIED').order_by('-created_at').first()
            if record and (timezone.now() - record.created_at).total_seconds() > 900:
                record = None

        if record:
            is_verified = True
            meta = record.metadata or {}
            name = name or meta.get('full_name') or meta.get('name')
            phone = phone or meta.get('phone_number') or meta.get('phone')
            email = email or meta.get('email')
            address = address or meta.get('address')
            shop_id = shop_id or meta.get('shop_id') or meta.get('shop_code')

        if not is_verified and otp:
            verify_res = OTPService.verify_otp(
                raw_otp=otp,
                purpose='CUSTOMER_REGISTRATION',
                verification_id=verification_id or None,
                email=email or None,
                shop_id=shop_id or None,
                phone_number=phone or None
            )
            if verify_res.get('success'):
                is_verified = True
            else:
                return JsonResponse({'error': f"Verification failed: {verify_res.get('error')}"}, status=400)

        if not is_verified:
            return JsonResponse({
                'error': 'Customer registration denied: You must verify the customer Gmail address with OTP before saving the customer record.'
            }, status=403)

        if not phone or not re.match(r'^\d{10}$', phone):
            return JsonResponse({'error': 'A valid 10-digit mobile number is required.'}, status=400)

        shop = None
        if shop_id:
            shop = Shop.objects.using('default').filter(code__iexact=shop_id).first()
            if not shop and _is_valid_uuid(shop_id):
                shop = Shop.objects.using('default').filter(id=shop_id).first()
        if not shop:
            shop = Shop.objects.using('default').first()

        # Identify registering cashier / worker
        worker_val = (data.get('worker_id') or data.get('worker_username') or data.get('cashier_id') or '').strip()
        worker_user = None
        if worker_val:
            worker_user = User.objects.using('default').filter(username__iexact=worker_val).first()
            if not worker_user:
                # Look for username extracted from composite string e.g. 'Aditya (cashier_b) (SB-EMP-001)'
                matches = re.findall(r'\(([^)]+)\)', worker_val)
                for candidate in matches:
                    u = User.objects.using('default').filter(username__iexact=candidate.strip()).first()
                    if u:
                        worker_user = u
                        break
            if not worker_user and ' ' in worker_val:
                first_tok = worker_val.split()[0]
                worker_user = User.objects.using('default').filter(first_name__iexact=first_tok).first()
        if not worker_user and getattr(request, 'user', None) and getattr(request.user, 'is_authenticated', False):
            if getattr(request.user, 'role', '') == User.Role.WORKER:
                worker_user = request.user
        if not worker_user and shop:
            membership = ShopMembership.objects.using('default').filter(shop=shop, is_active=True).first()
            if membership:
                worker_user = membership.user
        if not worker_user:
            worker_user = User.objects.using('default').filter(role=User.Role.WORKER).first()

        # Prevent duplicates within shop / update store link
        if CustomerProfile.objects.using('default').filter(phone_number=phone).exists():
            existing = CustomerProfile.objects.using('default').filter(phone_number=phone).first()
            if shop and not existing.registered_at_shop:
                existing.registered_at_shop = shop
                existing.save(using='default', update_fields=['registered_at_shop'])
            if worker_user and not existing.created_by_worker:
                existing.created_by_worker = worker_user
                existing.save(using='default', update_fields=['created_by_worker'])
            
            if shop:
                try:
                    from apps.customers.models import CustomerShopAccount
                    CustomerShopAccount.objects.using('default').get_or_create(
                        customer=existing,
                        shop=shop,
                        defaults={'visit_count': 1, 'last_visit': timezone.now()}
                    )
                except Exception:
                    pass

            reg_shop = existing.registered_at_shop or shop
            reg_worker = existing.created_by_worker or worker_user
            return JsonResponse({
                'success': True,
                'message': 'Customer already exists.',
                'customer': {
                    'id': str(existing.id),
                    'customer_code': existing.customer_code,
                    'name': existing.full_name,
                    'phone': existing.phone_number,
                    'email': existing.email,
                    'shop_id': str(reg_shop.id) if reg_shop else '',
                    'shop_code': reg_shop.code if reg_shop else '',
                    'shop_name': reg_shop.name if reg_shop else '',
                    'registered_by': reg_worker.get_full_name() or reg_worker.username if reg_worker else 'Cashier / POS Staff',
                    'is_verified': True
                }
            })

        with transaction.atomic(using='default'):
            cust_count = CustomerProfile.objects.using('default').count() + 1
            cust_code = f"SB-CUST-{cust_count:04d}"
            while CustomerProfile.objects.using('default').filter(customer_code=cust_code).exists():
                cust_count += 1
                cust_code = f"SB-CUST-{cust_count:04d}"

            # Create User for customer
            cust_username = f"cust_{phone}"
            cust_user = User.objects.using('default').filter(username=cust_username).first()
            if not cust_user:
                name_parts = (name or '').strip().split(' ', 1)
                f_name = name_parts[0] if name_parts else 'Valued'
                l_name = name_parts[1] if len(name_parts) > 1 else 'Customer'
                cust_user = User.objects.db_manager('default').create_user(
                    username=cust_username,
                    email=email or f"{phone}@smartbazaar.local",
                    password=secrets.token_hex(8),
                    role=User.Role.CUSTOMER,
                    phone_number=phone,
                    first_name=f_name,
                    last_name=l_name,
                    is_active=True,
                    is_verified=True
                )

            customer = CustomerProfile.objects.using('default').filter(user=cust_user).first()
            if not customer:
                customer = CustomerProfile.objects.using('default').create(
                    user=cust_user,
                    customer_code=cust_code,
                    full_name=name or 'Valued Customer',
                    phone_number=phone,
                    email=email,
                    registered_at_shop=shop,
                    created_by_worker=worker_user,
                    is_active=True
                )

            if shop:
                try:
                    from apps.customers.models import CustomerShopAccount
                    CustomerShopAccount.objects.using('default').get_or_create(
                        customer=customer,
                        shop=shop,
                        defaults={'visit_count': 1, 'last_visit': timezone.now()}
                    )
                except Exception:
                    pass

        reg_worker = customer.created_by_worker
        logger.info(f"✓ Registered active Customer: {name} ({phone}) at shop: {getattr(shop, 'code', 'N/A')}")
        return JsonResponse({
            'success': True,
            'message': f"Customer '{name}' verified and registered successfully.",
            'customer': {
                'id': str(customer.id),
                'customer_code': cust_code,
                'name': customer.full_name,
                'phone': customer.phone_number,
                'email': customer.email,
                'shop_id': str(shop.id) if shop else '',
                'shop_code': shop.code if shop else '',
                'shop_name': shop.name if shop else '',
                'registered_by': reg_worker.get_full_name() or reg_worker.username if reg_worker else 'Cashier / POS Staff',
                'is_verified': True
            }
        })

    except Exception as ex:
        logger.error(f"Failed to register customer: {ex}", exc_info=True)
        return JsonResponse({'error': f"Failed to register customer: {str(ex)}"}, status=400)


@csrf_exempt
def api_shop_customers_list(request):
    """
    GET /api/shop/customers/
    GET /api/shop/customers/list/
    Lists all registered customers associated with the requested shop.
    """
    shop_key = (request.GET.get('shop_code') or request.GET.get('shop_id') or '').strip()
    qs = CustomerProfile.objects.using('default').select_related('registered_at_shop', 'created_by_worker').order_by('-created_at')

    if shop_key:
        shop = Shop.objects.using('default').filter(code__iexact=shop_key).first() or Shop.objects.using('default').filter(id=shop_key).first()
        if shop:
            qs = qs.filter(models.Q(registered_at_shop=shop) | models.Q(shop_accounts__shop=shop)).distinct()

    results = []
    for c in qs:
        reg_shop = c.registered_at_shop
        reg_worker = c.created_by_worker
        worker_label = (reg_worker.get_full_name() or reg_worker.username) if reg_worker else 'Cashier / POS Staff'
        results.append({
            'id': str(c.id),
            'customer_code': c.customer_code,
            'name': c.full_name,
            'phone': c.phone_number,
            'email': c.email,
            'shop_id': str(reg_shop.id) if reg_shop else '',
            'shop_code': reg_shop.code if reg_shop else '',
            'shop_name': reg_shop.name if reg_shop else '',
            'registered_by': worker_label,
            'registered_by_id': reg_worker.username if reg_worker else '',
            'total_spent': float(c.total_spent or 0.0),
            'visit_count': int(c.visit_count or 0),
            'reward_points': int(c.reward_points or 0),
            'joined': c.created_at.strftime('%d %b %Y, %I:%M %p') if c.created_at else 'Recent',
            'is_verified': True
        })
    return JsonResponse({'success': True, 'customers': results, 'count': len(results)})


# =========================================================================
# EMAIL SERVICE TEST ENDPOINT
# =========================================================================

@csrf_exempt
def api_email_send_test(request):
    """
    POST /api/email/send-test
    Tests Gmail API OAuth authorization and message delivery.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST method required'}, status=405)

    data = _parse_body(request)
    recipient = data.get('recipient_email', '').strip().lower() or data.get('email', '').strip().lower()

    if not recipient or '@' not in recipient:
        return JsonResponse({'error': 'A valid recipient_email is required.'}, status=400)

    res = EmailService.sendTestEmail(recipient)

    status_code = 200 if res.get('success') else 400
    return JsonResponse(res, status=status_code)
