from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient
from apps.accounts.models import User, CustomerProfile, OTPVerification
from apps.shops.models import Shop, ShopMembership

class CustomerAuthenticationTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_customer_gmail_otp_login_flow(self):
        """Test customer passwordless login using Gmail OTP only."""
        # 1. Send OTP
        res = self.client.post('/api/auth/send-otp/', {'email': 'testuser@gmail.com', 'purpose': 'LOGIN'})
        self.assertEqual(res.status_code, 200)
        self.assertIn('dev_otp', res.data)
        otp = res.data['dev_otp']

        # 2. Verify with wrong OTP
        wrong_res = self.client.post('/api/auth/verify-otp/', {'email': 'testuser@gmail.com', 'otp': '000000'})
        self.assertEqual(wrong_res.status_code, 400)
        self.assertIn('Incorrect OTP', wrong_res.data['error'])

        # 3. Verify with correct OTP
        ok_res = self.client.post('/api/auth/verify-otp/', {
            'email': 'testuser@gmail.com',
            'otp': otp,
            'full_name': 'Test Customer',
            'phone_number': '9876543210'
        })
        self.assertEqual(ok_res.status_code, 200)
        self.assertIn('tokens', ok_res.data)
        self.assertIn('access', ok_res.data['tokens'])

        # Verify customer has NO usable password
        user = User.objects.get(email='testuser@gmail.com')
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.role, User.Role.CUSTOMER)

        # Profile created with unique customer code
        profile = CustomerProfile.objects.get(user=user)
        self.assertTrue(profile.customer_code.startswith('SB-CUST-'))
        self.assertEqual(profile.full_name, 'Test Customer')

    def test_worker_assisted_customer_registration(self):
        """Worker registers new customer: sends OTP, prevents duplicates, identifies existing."""
        # Create Worker and Shop
        owner = User.objects.create_user(username='shopowner', email='owner@smartbazaar.com', password='OwnerPassword123!', role=User.Role.SHOP_OWNER)
        shop = Shop.objects.create(owner=owner, name='Super Grocery', code='SB-SHOP-1001', phone='9999999999', city='Kolkata', address='Salt Lake')
        worker = User.objects.create_user(username='cashier1', email='cashier@smartbazaar.com', password='WorkerPassword123!', role=User.Role.WORKER)
        ShopMembership.objects.create(shop=shop, user=worker, role_in_shop=ShopMembership.RoleInShop.CASHIER)

        self.client.force_authenticate(user=worker)

        # 1. Search for non-existent customer
        search_res = self.client.get('/api/auth/customers/search/?phone=9876500000')
        self.assertEqual(search_res.status_code, 200)
        self.assertFalse(search_res.data['exists'])

        # 2. Worker initiates assisted registration
        reg_res = self.client.post('/api/auth/customers/register/', {
            'full_name': 'Ananya Roy',
            'phone_number': '9876500000',
            'email': 'ananya.roy@gmail.com',
            'consent_given': True
        })
        self.assertEqual(reg_res.status_code, 200)
        otp = reg_res.data['dev_otp']

        # 3. Verify OTP
        verify_res = self.client.post('/api/auth/verify-otp/', {
            'email': 'ananya.roy@gmail.com',
            'otp': otp,
            'full_name': 'Ananya Roy',
            'phone_number': '9876500000'
        })
        self.assertEqual(verify_res.status_code, 200)

        # 4. Search again - must find the registered customer
        search_again = self.client.get('/api/auth/customers/search/?phone=9876500000')
        self.assertEqual(search_again.status_code, 200)
        self.assertTrue(search_again.data['exists'])
        self.assertEqual(search_again.data['customer']['full_name'], 'Ananya Roy')
        # Masked fields
        self.assertIn('******', search_again.data['customer']['masked_phone'])

        # 5. Prevent duplicate registration with same mobile or email
        dup_res = self.client.post('/api/auth/customers/register/', {
            'full_name': 'Another Person',
            'phone_number': '9876500000',
            'email': 'different@gmail.com',
            'consent_given': True
        })
        self.assertEqual(dup_res.status_code, 409)

