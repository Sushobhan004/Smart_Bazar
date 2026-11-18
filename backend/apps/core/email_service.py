# -*- coding: utf-8 -*-
"""
Smart Bazaar — Official Gmail API Email Service
Implements Google OAuth 2.0 authorization, token refresh management,
base64url MIME message compilation, and robust API delivery logging.
"""

import os
import sys
import time
import json
import base64
import logging
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests
from django.conf import settings
from django.utils import timezone
from django.template.loader import render_to_string

logger = logging.getLogger('smart_bazaar.email')


class EmailService:
    """
    Centralized email delivery engine for Smart Bazaar using Google Gmail API.
    Scope: https://www.googleapis.com/auth/gmail.send
    """
    TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    GMAIL_SEND_ENDPOINT = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
    SCOPE = "https://www.googleapis.com/auth/gmail.send"

    _access_token = None
    _token_expiry = 0

    @classmethod
    def get_credentials(cls) -> dict:
        """Fetch credentials from environment or Django settings."""
        return {
            'client_id': os.getenv('GMAIL_CLIENT_ID', getattr(settings, 'GMAIL_CLIENT_ID', '')).strip(),
            'client_secret': os.getenv('GMAIL_CLIENT_SECRET', getattr(settings, 'GMAIL_CLIENT_SECRET', '')).strip(),
            'redirect_uri': os.getenv('GMAIL_REDIRECT_URI', getattr(settings, 'GMAIL_REDIRECT_URI', 'https://developers.google.com/oauthplayground')).strip(),
            'refresh_token': os.getenv('GMAIL_REFRESH_TOKEN', getattr(settings, 'GMAIL_REFRESH_TOKEN', '')).strip(),
            'sender_email': os.getenv('GMAIL_SENDER_EMAIL', getattr(settings, 'GMAIL_SENDER_EMAIL', 'smartbazaar.official@gmail.com')).strip(),
        }

    @classmethod
    def refresh_access_token(cls) -> str:
        """
        Refreshes short-lived Google OAuth 2.0 access token using the stored refresh_token.
        Caches in-memory until 60 seconds before expiration.
        """
        now = time.time()
        if cls._access_token and now < (cls._token_expiry - 60):
            return cls._access_token

        creds = cls.get_credentials()
        client_id = creds['client_id']
        client_secret = creds['client_secret']
        refresh_token = creds['refresh_token']

        if not client_id or not client_secret or not refresh_token:
            missing = []
            if not client_id: missing.append('GMAIL_CLIENT_ID')
            if not client_secret: missing.append('GMAIL_CLIENT_SECRET')
            if not refresh_token: missing.append('GMAIL_REFRESH_TOKEN')
            raise ValueError(f"Missing Gmail API OAuth credentials in backend environment: {', '.join(missing)}")

        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'refresh_token': refresh_token,
            'grant_type': 'refresh_token'
        }
        headers = {'Content-Type': 'application/x-www-form-urlencoded'}

        try:
            resp = requests.post(cls.TOKEN_ENDPOINT, data=payload, headers=headers, timeout=15)
        except Exception as e:
            logger.error(f"Network error contacting Google OAuth token endpoint: {e}")
            raise RuntimeError(f"Failed to connect to Google OAuth server: {e}")

        if resp.status_code != 200:
            err_data = resp.text
            try:
                err_json = resp.json()
                err_data = err_json.get('error_description', err_json.get('error', err_data))
            except Exception:
                pass
            logger.error(f"Google OAuth token refresh rejected ({resp.status_code}): {err_data}")
            raise RuntimeError(f"Google OAuth authorization failure ({resp.status_code}): {err_data}")

        data = resp.json()
        cls._access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)
        cls._token_expiry = now + expires_in
        logger.info(f"Successfully refreshed Google Gmail API access token (valid for {expires_in}s)")
        return cls._access_token

    @classmethod
    def _create_mime_message(cls, to_email: str, subject: str, html_body: str, plain_body: str, attachments: list = None) -> str:
        """Constructs an RFC 2822 MIME message (with optional attachments) and returns base64url encoded string."""
        from email.mime.application import MIMEApplication

        creds = cls.get_credentials()
        sender = creds['sender_email']

        if attachments:
            msg = MIMEMultipart('mixed')
            msg['Subject'] = subject
            msg['From'] = f"Smart Bazaar Official <{sender}>"
            msg['To'] = to_email

            alt_part = MIMEMultipart('alternative')
            if plain_body:
                alt_part.attach(MIMEText(plain_body, 'plain', 'utf-8'))
            if html_body:
                alt_part.attach(MIMEText(html_body, 'html', 'utf-8'))
            msg.attach(alt_part)

            for att in attachments:
                att_bytes = att.get('content')
                att_filename = att.get('filename', 'attachment.pdf')
                if att_bytes:
                    part = MIMEApplication(att_bytes, Name=att_filename)
                    part['Content-Disposition'] = f'attachment; filename="{att_filename}"'
                    msg.attach(part)
        else:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"Smart Bazaar Official <{sender}>"
            msg['To'] = to_email

            if plain_body:
                msg.attach(MIMEText(plain_body, 'plain', 'utf-8'))
            if html_body:
                msg.attach(MIMEText(html_body, 'html', 'utf-8'))

        raw_bytes = msg.as_bytes()
        return base64.urlsafe_b64encode(raw_bytes).decode('utf-8')

    @classmethod
    def _send_via_gmail_api(cls, recipient: str, subject: str, html_body: str, plain_body: str, purpose: str, shop_id: str = None, attachments: list = None) -> dict:
        """
        Core worker that compiles message, executes Gmail API POST, and records audit delivery log.
        """
        from apps.accounts.models import EmailDeliveryLog

        creds = cls.get_credentials()
        delivery_log = EmailDeliveryLog(
            recipient=recipient,
            subject=subject,
            purpose=purpose,
            provider='GMAIL_API',
            status='PENDING',
            shop_id=shop_id
        )

        try:
            # 1. Acquire valid access token
            access_token = cls.refresh_access_token()

            # 2. Compile base64url RFC 2822 payload (with optional PDF attachments)
            raw_b64 = cls._create_mime_message(recipient, subject, html_body, plain_body, attachments=attachments)

            # 3. Post to Google Gmail API
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            body = json.dumps({'raw': raw_b64})

            resp = requests.post(cls.GMAIL_SEND_ENDPOINT, data=body, headers=headers, timeout=20)
            if resp.status_code in (200, 201):
                resp_json = resp.json()
                msg_id = resp_json.get('id', 'N/A')
                thread_id = resp_json.get('threadId', 'N/A')
                delivery_log.status = 'SENT'
                delivery_log.gmail_message_id = msg_id
                delivery_log.save()
                logger.info(f"✓ Gmail API email successfully delivered to {recipient} (MsgID: {msg_id})")
                return {
                    'success': True,
                    'provider': 'GMAIL_API',
                    'message_id': msg_id,
                    'thread_id': thread_id,
                    'error': None
                }
            else:
                err_text = resp.text
                try:
                    err_json = resp.json()
                    err_text = err_json.get('error', {}).get('message', err_text)
                except Exception:
                    pass
                delivery_log.status = 'FAILED'
                delivery_log.error_message = f"Gmail API HTTP {resp.status_code}: {err_text}"
                delivery_log.save()
                logger.error(f"✗ Gmail API send failed for {recipient}: {err_text}")
                return {
                    'success': False,
                    'provider': 'GMAIL_API',
                    'status_code': resp.status_code,
                    'error': f"Gmail API Error ({resp.status_code}): {err_text}",
                    'message_id': None
                }

        except Exception as ex:
            error_msg = str(ex)
            delivery_log.status = 'FAILED'
            delivery_log.error_message = error_msg
            delivery_log.save()
            logger.warning(f"Gmail API execution error for {recipient} ({purpose}): {error_msg}")
            return {
                'success': False,
                'provider': 'GMAIL_API',
                'error': error_msg,
                'message_id': None
            }

    # ==================== 1. VERIFICATION OTP ====================
    @classmethod
    def sendVerificationOTP(cls, email: str, recipient_name: str, raw_otp: str, purpose: str, expiry_minutes: int = 5, shop_name: str = "Smart Bazaar", shop_id: str = None) -> dict:
        """
        Sends 6-digit OTP email using official Smart Bazaar HTML template via Gmail API.
        Supported purposes: OWNER_REGISTRATION, EMPLOYEE_REGISTRATION, CUSTOMER_REGISTRATION.
        """
        now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject = f"Smart Bazaar Verification Code: {raw_otp}"

        context = {
            'email_title': 'Smart Bazaar Account Verification',
            'recipient_name': recipient_name or 'User',
            'recipient_email': email,
            'raw_otp': raw_otp,
            'expiry_minutes': expiry_minutes,
            'shop_name': shop_name,
            'timestamp': now_str,
            'header_subtitle': f"Verification Code ({purpose.replace('_', ' ').title()})"
        }

        template_name = 'emails/owner_otp.html'
        if purpose == 'EMPLOYEE_REGISTRATION':
            template_name = 'emails/employee_otp.html'
        elif purpose == 'CUSTOMER_REGISTRATION':
            template_name = 'emails/customer_otp.html'

        try:
            html_body = render_to_string(template_name, context)
        except Exception:
            # Fallback inline HTML if template loader fails in standalone scripts
            html_body = f"""
            <div style="font-family: sans-serif; padding: 20px; background: #F8FAFC;">
                <div style="max-width: 500px; margin: 0 auto; background: white; padding: 25px; border-radius: 12px; border: 1px solid #E2E8F0;">
                    <h2 style="color: #0F5132; margin-top: 0;">🛍️ Smart Bazaar</h2>
                    <p>Hello <strong>{recipient_name or 'User'}</strong>,</p>
                    <p>Your one-time verification code for <strong>{purpose}</strong> is:</p>
                    <div style="font-size: 32px; font-weight: 800; letter-spacing: 6px; color: #0F5132; background: #F0FDF4; padding: 15px; text-align: center; border-radius: 8px; border: 2px dashed #0F5132;">
                        {raw_otp}
                    </div>
                    <p style="font-size: 12px; color: #64748B; margin-top: 15px;">Valid for {expiry_minutes} minutes. Never share this code with anyone.</p>
                </div>
            </div>
            """

        plain_body = (
            f"Smart Bazaar Verification Code\n\n"
            f"Hello {recipient_name or 'User'},\n"
            f"Your one-time verification code for {purpose} is: {raw_otp}\n"
            f"This code expires in {expiry_minutes} minutes.\n"
            f"Never share this code with anyone.\n"
        )

        return cls._send_via_gmail_api(email, subject, html_body, plain_body, purpose, shop_id=shop_id)

    # ==================== 2. SHOP OWNER WELCOME / ACTIVATION ====================
    @classmethod
    def sendAccountActivationEmail(cls, email: str, owner_name: str, shop_name: str, owner_id: str, shop_id: str, login_id: str, temp_password: str, login_url: str = None) -> dict:
        """
        Sends Welcome & Provisioning credentials email to newly activated Shop Owner.
        """
        now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject = f"Welcome to Smart Bazaar — Store Account Created for {shop_name}"
        login_url = login_url or "http://127.0.0.1:8000/"

        context = {
            'email_title': f"Store Provisioned: {shop_name}",
            'owner_name': owner_name,
            'shop_name': shop_name,
            'owner_id': owner_id,
            'shop_id': shop_id,
            'login_id': login_id,
            'temp_password': temp_password,
            'login_url': login_url,
            'timestamp': now_str,
            'header_subtitle': "Store Owner Account Activation"
        }

        try:
            html_body = render_to_string('emails/owner_welcome.html', context)
        except Exception:
            html_body = f"""
            <div style="font-family: sans-serif; padding: 20px; background: #F8FAFC;">
                <div style="max-width: 550px; margin: 0 auto; background: white; padding: 25px; border-radius: 12px;">
                    <h2 style="color: #0F5132;">Welcome to Smart Bazaar, {owner_name}!</h2>
                    <p>Your shop <strong>{shop_name}</strong> ({shop_id}) has been created with a dedicated database.</p>
                    <p><strong>Login ID:</strong> {login_id}</p>
                    <p><strong>Temporary Password:</strong> {temp_password}</p>
                    <p><a href="{login_url}">Click here to log in</a></p>
                </div>
            </div>
            """

        plain_body = (
            f"Welcome to Smart Bazaar!\n\n"
            f"Store Name: {shop_name}\n"
            f"Store ID: {shop_id}\n"
            f"Owner ID: {owner_id}\n"
            f"Login ID: {login_id}\n"
            f"Temporary Password: {temp_password}\n"
            f"Portal URL: {login_url}\n\n"
            f"Please change your password after initial sign in.\n"
        )

        return cls._send_via_gmail_api(email, subject, html_body, plain_body, 'OWNER_ACTIVATION', shop_id=shop_id)

    # ==================== 3. EMPLOYEE WELCOME ====================
    @classmethod
    def sendEmployeeWelcomeEmail(cls, email: str, employee_name: str, shop_name: str, employee_id: str, login_id: str, role: str, temp_password: str, login_url: str = None, shop_id: str = None) -> dict:
        """
        Sends Welcome and POS credentials email to newly registered Staff / Cashier.
        """
        now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject = f"Smart Bazaar Staff Credentials: {shop_name}"
        login_url = login_url or "http://127.0.0.1:8000/"

        context = {
            'email_title': f"Staff Account: {shop_name}",
            'employee_name': employee_name,
            'shop_name': shop_name,
            'shop_id': shop_id or 'STORE',
            'employee_id': employee_id,
            'login_id': login_id,
            'role': role,
            'temp_password': temp_password,
            'login_url': login_url,
            'timestamp': now_str,
            'header_subtitle': "Store Staff Access Credentials"
        }

        try:
            html_body = render_to_string('emails/employee_welcome.html', context)
        except Exception:
            html_body = f"""
            <div style="font-family: sans-serif; padding: 20px;">
                <h2>Welcome to Smart Bazaar, {employee_name}!</h2>
                <p>You have been assigned to <strong>{shop_name}</strong> as <strong>{role}</strong>.</p>
                <p>Employee ID: {employee_id} | Login ID: {login_id}</p>
                <p>Temporary Password: {temp_password}</p>
                <p><a href="{login_url}">Log in to POS Terminal</a></p>
            </div>
            """

        plain_body = (
            f"Welcome to Smart Bazaar Staff Team!\n\n"
            f"Employee: {employee_name}\n"
            f"Store: {shop_name}\n"
            f"Employee ID: {employee_id}\n"
            f"Login ID: {login_id}\n"
            f"Assigned Role: {role}\n"
            f"Temporary Password: {temp_password}\n"
            f"Login URL: {login_url}\n"
        )

        return cls._send_via_gmail_api(email, subject, html_body, plain_body, 'EMPLOYEE_WELCOME', shop_id=shop_id)

    # ==================== 4. CUSTOMER VERIFICATION ====================
    @classmethod
    def sendCustomerVerificationEmail(cls, email: str, customer_name: str, raw_otp: str, shop_name: str = "Smart Bazaar", expiry_minutes: int = 5, shop_id: str = None) -> dict:
        """
        Sends Customer OTP email during checkout registration.
        """
        return cls.sendVerificationOTP(
            email=email,
            recipient_name=customer_name or 'Valued Customer',
            raw_otp=raw_otp,
            purpose='CUSTOMER_REGISTRATION',
            expiry_minutes=expiry_minutes,
            shop_name=shop_name,
            shop_id=shop_id
        )

    # ==================== 5. ACCOUNT SECURITY NOTIFICATION ====================
    @classmethod
    def sendAccountSecurityNotification(cls, email: str, user_name: str, event_description: str, ip_address: str = None, user_agent: str = None) -> dict:
        """
        Sends an alert when sensitive account events occur (password reset, status toggle, login from new device).
        """
        now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject = f"Smart Bazaar Security Alert: {event_description}"

        context = {
            'email_title': 'Security Notification',
            'user_name': user_name or 'User',
            'event_description': event_description,
            'ip_address': ip_address or 'Unknown',
            'user_agent': user_agent or 'Standard Client',
            'timestamp': now_str,
            'header_subtitle': 'Account Security Alert'
        }

        try:
            html_body = render_to_string('emails/security_notification.html', context)
        except Exception:
            html_body = f"""
            <div style="font-family: sans-serif; padding: 20px;">
                <h3 style="color: #DC2626;">Smart Bazaar Security Notification</h3>
                <p>Hello {user_name},</p>
                <p>Security Event: <strong>{event_description}</strong></p>
                <p>IP Address: {ip_address} | Time: {now_str}</p>
            </div>
            """

        plain_body = (
            f"Smart Bazaar Security Notification\n\n"
            f"User: {user_name}\n"
            f"Event: {event_description}\n"
            f"IP Address: {ip_address}\n"
            f"Time: {now_str}\n"
        )

        return cls._send_via_gmail_api(email, subject, html_body, plain_body, 'SECURITY_ALERT')

    # ==================== 6. CUSTOMER BILL RECEIPT WITH PDF & WATERMARK ====================
    @classmethod
    def sendCustomerBillReceiptEmail(
        cls,
        recipient_email: str,
        customer_name: str,
        customer_phone: str,
        customer_code: str,
        shop_name: str,
        shop_code: str,
        shop_owner_name: str,
        shop_address: str,
        shop_phone: str,
        cashier_name: str,
        cashier_id: str,
        bill_number: str,
        items: list,
        subtotal: float,
        tax_amount: float,
        final_total: float,
        payment_method: str = "UPI / Cash",
        created_at_str: str = None,
        pdf_bytes: bytes = None,
        shop_id: str = None
    ) -> dict:
        """
        Dispatches official Tax Invoice Receipt to customer's registered Gmail with:
        - Store Name, ID, Address, Phone
        - Store Owner Full Name
        - Cashier Full Name & ID who billed it
        - Customer details
        - Itemized purchase breakdown
        - Attached high-res PDF with authentic Store Logo watermark
        """
        now_str = created_at_str or timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject = f"Invoice #{bill_number} from {shop_name} — Thank You for Shopping!"

        # Build items table rows HTML
        items_rows_html = ""
        items_plain = ""
        for idx, it in enumerate(items, 1):
            name = it.get('name', 'Item')
            qty = it.get('qty', 1)
            price = float(it.get('price', 0.0))
            total = float(it.get('total', price * qty))
            items_rows_html += f"""
            <tr style="border-bottom: 1px solid #E2E8F0;">
                <td style="padding: 10px 12px; font-size: 13px; color: #1E293B;">{idx}. {name}</td>
                <td style="padding: 10px 12px; font-size: 13px; color: #475569; text-align: center;">{qty}</td>
                <td style="padding: 10px 12px; font-size: 13px; color: #475569; text-align: right;">₹{price:.2f}</td>
                <td style="padding: 10px 12px; font-size: 13px; color: #0F172A; font-weight: 600; text-align: right;">₹{total:.2f}</td>
            </tr>
            """
            items_plain += f"{idx}. {name} x {qty} @ ₹{price:.2f} = ₹{total:.2f}\n"

        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Tax Invoice #{bill_number}</title>
        </head>
        <body style="margin: 0; padding: 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F1F5F9; color: #1E293B;">
            <div style="max-width: 620px; margin: 0 auto; background-color: #FFFFFF; border-radius: 14px; overflow: hidden; box-shadow: 0 4px 20px rgba(0,0,0,0.08); border: 1px solid #E2E8F0;">
                
                <!-- Header Banner -->
                <div style="background: linear-gradient(135deg, #0F5132 0%, #198754 100%); padding: 26px 30px; color: #FFFFFF;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <div>
                            <span style="font-size: 11px; text-transform: uppercase; letter-spacing: 1.5px; background: rgba(255,255,255,0.2); padding: 3px 8px; border-radius: 4px; font-weight: 700;">OFFICIAL TAX INVOICE</span>
                            <h1 style="margin: 8px 0 4px 0; font-size: 24px; font-weight: 800; color: #FFFFFF;">{shop_name}</h1>
                            <p style="margin: 0; font-size: 12px; color: #D1E7DD;">Store ID: <strong>{shop_code}</strong> | Phone: {shop_phone or 'N/A'}</p>
                            <p style="margin: 2px 0 0 0; font-size: 12px; color: #D1E7DD;">{shop_address or 'Store Location'}</p>
                        </div>
                    </div>
                </div>

                <!-- Bill & Personnel Highlights -->
                <div style="padding: 20px 30px 10px 30px; background: #F8FAFC; border-bottom: 1px solid #E2E8F0;">
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="width: 50%; vertical-align: top; padding-right: 12px;">
                                <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748B; font-weight: 700; margin-bottom: 4px;">STORE & PERSONNEL</div>
                                <div style="font-size: 13px; color: #0F172A; margin-bottom: 3px;">
                                    <strong>Shop Owner:</strong> <span style="color: #0F5132; font-weight: 700;">{shop_owner_name}</span>
                                </div>
                                <div style="font-size: 13px; color: #0F172A; margin-bottom: 3px;">
                                    <strong>Billed By (Cashier):</strong> <span style="font-weight: 600;">{cashier_name}</span> <span style="color: #64748B; font-size: 11px;">({cashier_id})</span>
                                </div>
                                <div style="font-size: 12px; color: #475569;">
                                    <strong>Payment Mode:</strong> {payment_method}
                                </div>
                            </td>
                            <td style="width: 50%; vertical-align: top; padding-left: 12px; border-left: 1px solid #E2E8F0;">
                                <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; color: #64748B; font-weight: 700; margin-bottom: 4px;">INVOICE & CUSTOMER</div>
                                <div style="font-size: 13px; color: #0F172A; margin-bottom: 3px;">
                                    <strong>Invoice #:</strong> <span style="font-family: monospace; font-weight: 700; color: #0F5132;">{bill_number}</span>
                                </div>
                                <div style="font-size: 12px; color: #475569; margin-bottom: 3px;">
                                    <strong>Date & Time:</strong> {now_str}
                                </div>
                                <div style="font-size: 13px; color: #0F172A; margin-bottom: 2px;">
                                    <strong>Customer:</strong> <span style="font-weight: 600;">{customer_name or 'Valued Customer'}</span>
                                </div>
                                <div style="font-size: 12px; color: #64748B;">
                                    Phone: {customer_phone or 'N/A'} | ID: {customer_code or 'REG'}
                                </div>
                            </td>
                        </tr>
                    </table>
                </div>

                <!-- Items Breakdown -->
                <div style="padding: 24px 30px;">
                    <div style="font-size: 12px; text-transform: uppercase; letter-spacing: 0.8px; color: #475569; font-weight: 700; margin-bottom: 12px;">ITEMIZED PURCHASE DETAILS</div>
                    <table style="width: 100%; border-collapse: collapse; background: #FFFFFF; border-radius: 8px; overflow: hidden; border: 1px solid #E2E8F0;">
                        <thead>
                            <tr style="background: #F1F5F9; color: #475569; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px;">
                                <th style="padding: 10px 12px; text-align: left; font-weight: 700;">Product</th>
                                <th style="padding: 10px 12px; text-align: center; font-weight: 700; width: 50px;">Qty</th>
                                <th style="padding: 10px 12px; text-align: right; font-weight: 700; width: 80px;">Rate</th>
                                <th style="padding: 10px 12px; text-align: right; font-weight: 700; width: 90px;">Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            {items_rows_html}
                        </tbody>
                    </table>

                    <!-- Totals Box -->
                    <div style="margin-top: 18px; display: flex; justify-content: flex-end;">
                        <table style="width: 260px; border-collapse: collapse; margin-left: auto;">
                            <tr>
                                <td style="padding: 4px 8px; font-size: 13px; color: #64748B;">Subtotal:</td>
                                <td style="padding: 4px 8px; font-size: 13px; color: #1E293B; text-align: right; font-weight: 600;">₹{subtotal:.2f}</td>
                            </tr>
                            <tr>
                                <td style="padding: 4px 8px; font-size: 13px; color: #64748B;">GST / Taxes:</td>
                                <td style="padding: 4px 8px; font-size: 13px; color: #1E293B; text-align: right; font-weight: 600;">₹{tax_amount:.2f}</td>
                            </tr>
                            <tr style="border-top: 2px solid #0F5132;">
                                <td style="padding: 8px 8px; font-size: 15px; color: #0F5132; font-weight: 800;">Grand Total:</td>
                                <td style="padding: 8px 8px; font-size: 18px; color: #0F5132; text-align: right; font-weight: 800;">₹{final_total:.2f}</td>
                            </tr>
                        </table>
                    </div>

                    <!-- Watermarked PDF Notification Callout -->
                    <div style="margin-top: 26px; padding: 14px 18px; background: #ECFDF5; border: 1px solid #A7F3D0; border-radius: 10px; display: flex; align-items: center;">
                        <div style="font-size: 24px; margin-right: 12px;">📄</div>
                        <div style="font-size: 12px; color: #065F46; line-height: 1.5;">
                            <strong>Official PDF Receipt Attached:</strong> A formal tax invoice PDF with authentic store watermark logo has been generated and attached to this email. You can view, download, or print it anytime for warranty and returns.
                        </div>
                    </div>
                </div>

                <!-- Footer -->
                <div style="background: #0F172A; padding: 18px 30px; text-align: center; color: #94A3B8; font-size: 11px; line-height: 1.6;">
                    <div style="color: #FFFFFF; font-weight: 700; margin-bottom: 2px;">Smart Bazaar Retail Network</div>
                    <div>This is an official automated digital invoice sent via Google Gmail API.</div>
                    <div style="margin-top: 4px; color: #64748B;">Thank you for shopping with {shop_name}!</div>
                </div>
            </div>
        </body>
        </html>
        """

        plain_body = f"""
============================================================
              {shop_name} — TAX INVOICE
============================================================
Store ID: {shop_code}
Store Address: {shop_address}
Store Phone: {shop_phone}

PERSONNEL DETAILS:
- Shop Owner: {shop_owner_name}
- Cashier Billed By: {cashier_name} ({cashier_id})

INVOICE DETAILS:
- Invoice #: {bill_number}
- Date/Time: {now_str}
- Payment Mode: {payment_method}

CUSTOMER DETAILS:
- Name: {customer_name}
- Phone: {customer_phone}
- Customer Code: {customer_code}

PURCHASE SUMMARY:
{items_plain}
------------------------------------------------------------
Subtotal:    ₹{subtotal:.2f}
GST / Taxes: ₹{tax_amount:.2f}
Grand Total: ₹{final_total:.2f}
============================================================
A formal PDF receipt with authentic store watermark is attached.
Thank you for shopping with {shop_name}!
        """

        attachments = []
        if pdf_bytes:
            attachments.append({
                'filename': f"Receipt_{bill_number}.pdf",
                'content': pdf_bytes,
                'mime_type': 'application/pdf'
            })

        return cls._send_via_gmail_api(
            recipient=recipient_email,
            subject=subject,
            html_body=html_body,
            plain_body=plain_body,
            purpose='CUSTOMER_BILL_RECEIPT',
            shop_id=shop_id,
            attachments=attachments
        )

    # ==================== 7. TEST EMAIL ====================
    @classmethod
    def sendTestEmail(cls, recipient_email: str) -> dict:
        """
        Sends a test email to verify Gmail API connectivity and Google OAuth token validity.
        """
        now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
        subject = f"Smart Bazaar Gmail API Test — {now_str}"
        html_body = f"""
        <div style="font-family: sans-serif; padding: 30px; background: #F8FAFC;">
            <div style="max-width: 550px; margin: 0 auto; background: white; padding: 30px; border-radius: 12px; border: 1px solid #E2E8F0;">
                <h2 style="color: #0F5132; margin-top: 0;">🛍️ Smart Bazaar Gmail API Test</h2>
                <p style="color: #15803D; font-weight: 700; font-size: 16px;">✓ Connection Successful!</p>
                <p>This email confirms that your Google Cloud OAuth 2.0 configuration and Gmail API authorization are working correctly on your Smart Bazaar instance.</p>
                <ul style="color: #475569; font-size: 13px;">
                    <li><strong>Provider:</strong> Official Google Gmail API (v1)</li>
                    <li><strong>Scope:</strong> https://www.googleapis.com/auth/gmail.send</li>
                    <li><strong>Timestamp:</strong> {now_str}</li>
                    <li><strong>Recipient:</strong> {recipient_email}</li>
                </ul>
                <div style="margin-top: 20px; font-size: 11px; color: #94A3B8;">Smart Bazaar Automated System Diagnostic</div>
            </div>
        </div>
        """
        plain_body = f"Smart Bazaar Gmail API Test\n\nConnection successful! Delivered at {now_str} to {recipient_email}."
        return cls._send_via_gmail_api(recipient_email, subject, html_body, plain_body, 'API_TEST')
