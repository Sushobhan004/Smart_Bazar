# -*- coding: utf-8 -*-
"""
Smart Bazaar — Central OTP Verification Engine
Enforces 6-digit secure generation, 5-minute expiry, 60-second cooldown,
5-attempt lockouts, strict purpose isolation, and backend-only validation.
"""

import sys
import re
import uuid
import secrets
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from apps.accounts.models import OTPVerification, EmailVerificationRecord
from apps.core.email_service import EmailService

logger = logging.getLogger('smart_bazaar.otp')


class OTPService:
    """
    Unified, cryptographically secure OTP engine for Smart Bazaar.
    """
    EXPIRY_MINUTES = 5
    COOLDOWN_SECONDS = 60
    MAX_ATTEMPTS = 5

    VALID_PURPOSES = {
        'OWNER_REGISTRATION',
        'EMPLOYEE_REGISTRATION',
        'CUSTOMER_REGISTRATION',
        'LOGIN',
        'REGISTRATION'
    }

    @staticmethod
    def normalize_email(email: str) -> str:
        """Normalizes and validates email string."""
        if not email or '@' not in str(email):
            raise ValueError("A valid email address is required.")
        return str(email).strip().lower()

    @classmethod
    def generate_and_send_otp(
        cls,
        email: str,
        purpose: str,
        recipient_name: str = "",
        phone_number: str = "",
        shop_id: str = None,
        account_id: str = None,
        metadata: dict = None
    ) -> dict:
        """
        Generates a 6-digit secure OTP, records hashed state, and dispatches via Gmail API.
        """
        clean_email = cls.normalize_email(email)

        if purpose not in cls.VALID_PURPOSES:
            raise ValueError(f"Invalid verification purpose: '{purpose}'. Must be one of {cls.VALID_PURPOSES}")

        now = timezone.now()

        # 1. Enforce 60-second resend cooldown
        recent_active = OTPVerification.objects.filter(
            email=clean_email,
            purpose=purpose,
            is_used=False,
            resend_available_at__gt=now
        ).first()

        if recent_active:
            wait_sec = max(1, int((recent_active.resend_available_at - now).total_seconds()))
            return {
                'success': False,
                'status': 'COOLDOWN',
                'wait_seconds': wait_sec,
                'error': f"Please wait {wait_sec} seconds before requesting a new verification code."
            }

        # 2. Invalidate any previous unverified OTPs for this email and purpose
        OTPVerification.objects.filter(
            email=clean_email,
            purpose=purpose,
            is_used=False
        ).update(is_used=True, status='EXPIRED')

        # 3. Generate 6-digit cryptographically secure OTP
        raw_otp = f"{secrets.randbelow(1000000):06d}"
        otp_hash = OTPVerification.hash_otp(raw_otp)

        # 4. Save hashed record to central database
        expires_at = now + timedelta(minutes=cls.EXPIRY_MINUTES)
        resend_at = now + timedelta(seconds=cls.COOLDOWN_SECONDS)

        record = OTPVerification.objects.create(
            email=clean_email,
            phone_number=str(phone_number).strip() if phone_number else None,
            otp_hash=otp_hash,
            purpose=purpose,
            status='PENDING',
            attempts_count=0,
            is_used=False,
            shop_id=str(shop_id) if shop_id else None,
            account_id=str(account_id) if account_id else None,
            metadata=metadata or {},
            expires_at=expires_at,
            resend_available_at=resend_at
        )

        logger.info(f"Generated secure OTP for {clean_email} [Purpose: {purpose}, ID: {record.id}]")

        # 5. Dispatch email via official Gmail API
        shop_name = (metadata or {}).get('shop_name', 'Smart Bazaar')
        email_result = EmailService.sendVerificationOTP(
            email=clean_email,
            recipient_name=recipient_name,
            raw_otp=raw_otp,
            purpose=purpose,
            expiry_minutes=cls.EXPIRY_MINUTES,
            shop_name=shop_name,
            shop_id=shop_id
        )

        # Dev / Testing support: keep raw_otp in metadata only during DEBUG or active test session
        response_data = {
            'success': True,
            'verification_id': str(record.id),
            'email': clean_email,
            'purpose': purpose,
            'expires_in_minutes': cls.EXPIRY_MINUTES,
            'resend_cooldown': cls.COOLDOWN_SECONDS,
            'gmail_delivery': email_result,
            'message': f"Verification code sent to {clean_email} via Gmail API."
        }

        # If in debug mode and email failed due to missing credentials, inform client cleanly
        if not email_result.get('success'):
            response_data['warning'] = email_result.get('error')

        # For testing convenience during development / DEBUG mode
        if getattr(settings, 'DEBUG', False) or 'test' in sys.argv or any('test' in arg for arg in sys.argv):
            response_data['dev_otp'] = raw_otp

        return response_data

    @classmethod
    def verify_otp(
        cls,
        raw_otp: str,
        purpose: str,
        verification_id: str = None,
        email: str = None,
        shop_id: str = None,
        phone_number: str = None
    ) -> dict:
        """
        Validates OTP strictly on backend:
        1. Checks existence of active verification record.
        2. Validates purpose isolation.
        3. Validates shop association if provided.
        4. Validates expiration.
        5. Validates attempt limits (max 5).
        6. Verifies cryptographic hash.
        """
        if not raw_otp or not str(raw_otp).strip():
            return {'success': False, 'error': 'Verification code cannot be empty.'}

        clean_otp = str(raw_otp).strip()

        # Find record by verification_id if provided (valid UUID), else by email + purpose
        query = OTPVerification.objects.filter(is_used=False)
        is_uuid = False
        if verification_id:
            try:
                uuid.UUID(str(verification_id).strip())
                is_uuid = True
            except Exception:
                is_uuid = False

        if verification_id and is_uuid:
            record = query.filter(id=verification_id).first()
        elif email:
            clean_email = cls.normalize_email(email)
            record = query.filter(email=clean_email, purpose=purpose).order_by('-created_at').first()
        elif phone_number:
            clean_phone = str(phone_number).strip()
            record = query.filter(phone_number=clean_phone, purpose=purpose).order_by('-created_at').first()
        else:
            return {'success': False, 'error': 'Either verification_id, email, or phone number must be provided.'}

        if not record:
            # Check if this OTP was already verified recently (within 15 minutes) for account creation
            clean_email = cls.normalize_email(email) if email else None
            verified_query = OTPVerification.objects.filter(purpose=purpose, status='VERIFIED')
            if verification_id and is_uuid:
                already_verified = verified_query.filter(id=verification_id).first()
            elif clean_email:
                already_verified = verified_query.filter(email=clean_email).order_by('-created_at').first()
            elif phone_number:
                already_verified = verified_query.filter(phone_number=str(phone_number).strip()).order_by('-created_at').first()
            else:
                already_verified = None

            if already_verified and (timezone.now() - already_verified.created_at).total_seconds() < 900:
                if already_verified.check_otp(clean_otp):
                    return {
                        'success': True,
                        'verification_id': str(already_verified.id),
                        'email': already_verified.email,
                        'purpose': already_verified.purpose,
                        'shop_id': already_verified.shop_id,
                        'metadata': already_verified.metadata,
                        'message': 'Gmail verification succeeded.'
                    }

            return {'success': False, 'error': 'No active verification session found. Please enter the newest 6-digit code received on your Gmail or request a new code.'}

        # 1. Purpose check
        if record.purpose != purpose:
            logger.warning(f"OTP purpose mismatch: expected {purpose}, found {record.purpose}")
            return {'success': False, 'error': f"Verification code was not issued for {purpose.replace('_', ' ').title()}."}

        # 2. Shop ID check (if record is bound to a specific shop)
        if record.shop_id and shop_id and str(record.shop_id) != str(shop_id):
            return {'success': False, 'error': "This verification code does not belong to your store."}

        # 3. Check attempt counter
        if record.attempts_count >= cls.MAX_ATTEMPTS:
            record.status = 'FAILED'
            record.is_used = True
            record.save(update_fields=['status', 'is_used'])
            return {'success': False, 'error': f"Maximum verification attempts ({cls.MAX_ATTEMPTS}) exceeded. This code is permanently locked."}

        # 4. Check expiration
        now = timezone.now()
        if now > record.expires_at:
            record.status = 'EXPIRED'
            record.is_used = True
            record.save(update_fields=['status', 'is_used'])
            return {'success': False, 'error': f"Verification code has expired ({cls.EXPIRY_MINUTES}-minute limit). Please request a new code."}

        # 5. Check hash comparison
        if not record.check_otp(clean_otp):
            record.attempts_count += 1
            remaining = cls.MAX_ATTEMPTS - record.attempts_count
            if record.attempts_count >= cls.MAX_ATTEMPTS:
                record.status = 'FAILED'
                record.is_used = True
                record.save(update_fields=['status', 'is_used', 'attempts_count'])
                return {'success': False, 'error': f"Incorrect code. Maximum attempts reached. Code has been invalidated."}
            record.save(update_fields=['attempts_count'])
            return {'success': False, 'error': f"Incorrect verification code. {remaining} attempt(s) remaining."}

        # 6. Verification Success!
        record.status = 'VERIFIED'
        record.is_used = True
        record.save(update_fields=['status', 'is_used'])
        logger.info(f"✓ OTP verified successfully for {record.email} [{purpose}]")

        return {
            'success': True,
            'verification_id': str(record.id),
            'email': record.email,
            'purpose': record.purpose,
            'shop_id': record.shop_id,
            'metadata': record.metadata,
            'message': 'Gmail verification succeeded.'
        }
