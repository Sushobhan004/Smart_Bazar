import uuid
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User, CustomerProfile
from apps.shops.models import Shop, ShopMembership
from apps.products.models import Product, ProductBarcode
from apps.inventory.models import Inventory
from apps.billing.models import Sale
from apps.customers.models import Offer, OfferEligibility

class BillingAndPOSWorkflowTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        # Create Owner and Shop
        self.owner = User.objects.create_user(username='shopowner1', email='owner1@test.com', password='Password123!', role=User.Role.SHOP_OWNER)
        self.shop = Shop.objects.create(
            owner=self.owner, name='Kolkata Mega Bazaar', code='SB-SHOP-2001',
            phone='9830098300', city='Kolkata', address='Park Street', upi_vpa='kolkatabazaar@okaxis'
        )
        # Create Worker
        self.worker = User.objects.create_user(username='worker1', email='worker1@test.com', password='Password123!', role=User.Role.WORKER)
        ShopMembership.objects.create(shop=self.shop, user=self.worker, role_in_shop=ShopMembership.RoleInShop.CASHIER)

        # Create Products
        self.prod1 = Product.objects.create(
            shop=self.shop, name='Fortune Sunlite Oil 1L', sku='SKU-FORT-01',
            selling_price=Decimal('150.00'), mrp=Decimal('175.00'), tax_rate=Decimal('5.00'), min_stock_alert=5
        )
        ProductBarcode.objects.create(product=self.prod1, barcode='8901234567890', is_primary=True)
        Inventory.objects.create(shop=self.shop, product=self.prod1, current_stock=Decimal('20.00'))

        self.prod2 = Product.objects.create(
            shop=self.shop, name='Aashirvaad Atta 5kg', sku='SKU-ATTA-05',
            selling_price=Decimal('250.00'), mrp=Decimal('280.00'), tax_rate=Decimal('0.00'), min_stock_alert=2
        )
        ProductBarcode.objects.create(product=self.prod2, barcode='8909876543210', is_primary=True)
        Inventory.objects.create(shop=self.shop, product=self.prod2, current_stock=Decimal('2.00'))

        # Create Customer
        self.cust_user = User.objects.create_user(username='cust_rahul', email='rahul@gmail.com', role=User.Role.CUSTOMER)
        self.customer = CustomerProfile.objects.create(
            user=self.cust_user, customer_code='SB-CUST-100200', full_name='Rahul Sen',
            phone_number='9831122334', email='rahul@gmail.com'
        )

        # Create Spend Offer: Spend ₹15,000 get ₹50 flat reward
        self.offer = Offer.objects.create(
            shop=self.shop, title='Mega ₹50 Voucher on ₹15k Spend', code='FESTIVE50',
            calculation_method=Offer.CalculationMethod.LIFETIME, min_spend_required=Decimal('15000.00'),
            discount_type=Offer.DiscountType.FLAT, reward_value=Decimal('50.00'),
            valid_from=timezone.now() - timezone.timedelta(days=1),
            valid_until=timezone.now() + timezone.timedelta(days=30)
        )

    def test_barcode_lookup(self):
        """Worker scans barcode - retrieves item details and current stock."""
        self.client.force_authenticate(user=self.worker)
        res = self.client.get(f'/api/products/barcode/8901234567890/?shop_id={self.shop.id}')
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data['found'])
        self.assertEqual(res.data['product']['name'], 'Fortune Sunlite Oil 1L')
        self.assertEqual(res.data['available_stock'], 20.0)

    def test_successful_bill_completion_and_stock_deduction(self):
        """Complete POS bill, check atomic inventory deduction, and invoice generation."""
        self.client.force_authenticate(user=self.worker)
        idem_key = str(uuid.uuid4())

        checkout_data = {
            'shop_id': str(self.shop.id),
            'customer_id': str(self.customer.id),
            'is_guest': False,
            'items': [
                {'product_id': str(self.prod1.id), 'quantity': '2.00'}, # 2 x 150 = 300 + 5% tax (15) = 315
                {'product_id': str(self.prod2.id), 'quantity': '1.00'}  # 1 x 250 = 250 + 0% tax = 250 -> Total = 565
            ],
            'payment_method': 'UPI',
            'idempotency_key': idem_key
        }

        res = self.client.post('/api/sales/checkout/', checkout_data, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data['final_total'], '565.00')
        self.assertTrue(res.data['bill_number'].startswith('SB-INV-'))

        # Verify atomic stock deduction
        inv1 = Inventory.objects.get(product=self.prod1)
        inv2 = Inventory.objects.get(product=self.prod2)
        self.assertEqual(inv1.current_stock, Decimal('18.00')) # 20 - 2 = 18
        self.assertEqual(inv2.current_stock, Decimal('1.00'))  # 2 - 1 = 1

        # Verify Customer spending updated
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.total_spent, Decimal('565.00'))
        self.assertEqual(self.customer.visit_count, 1)

    def test_insufficient_stock_prevention(self):
        """Cannot oversell stock. System blocks with 400 error."""
        self.client.force_authenticate(user=self.worker)
        res = self.client.post('/api/sales/checkout/', {
            'shop_id': str(self.shop.id),
            'is_guest': True,
            'items': [{'product_id': str(self.prod2.id), 'quantity': '10.00'}], # Only 2 in stock
            'payment_method': 'CASH',
            'idempotency_key': str(uuid.uuid4())
        }, format='json')

        self.assertEqual(res.status_code, 400)
        self.assertIn('Insufficient stock', res.data['error'])
        # Ensure stock was not changed
        inv2 = Inventory.objects.get(product=self.prod2)
        self.assertEqual(inv2.current_stock, Decimal('2.00'))

    def test_idempotency_protection(self):
        """Submitting with same idempotency key returns same invoice without duplicate deductions."""
        self.client.force_authenticate(user=self.worker)
        idem_key = str(uuid.uuid4())
        payload = {
            'shop_id': str(self.shop.id),
            'is_guest': True,
            'items': [{'product_id': str(self.prod1.id), 'quantity': '1.00'}],
            'payment_method': 'CASH',
            'idempotency_key': idem_key
        }

        res1 = self.client.post('/api/sales/checkout/', payload, format='json')
        self.assertEqual(res1.status_code, 201)

        res2 = self.client.post('/api/sales/checkout/', payload, format='json')
        self.assertEqual(res2.status_code, 200)
        self.assertEqual(res1.data['bill_number'], res2.data['bill_number'])

        # Stock deducted only once
        inv1 = Inventory.objects.get(product=self.prod1)
        self.assertEqual(inv1.current_stock, Decimal('19.00'))

    def test_guest_checkout_works(self):
        """Guest checkout does not require customer profile."""
        self.client.force_authenticate(user=self.worker)
        res = self.client.post('/api/sales/checkout/', {
            'shop_id': str(self.shop.id),
            'is_guest': True,
            'guest_name': 'Walk-in Guest',
            'items': [{'product_id': str(self.prod1.id), 'quantity': '1.00'}],
            'payment_method': 'CASH',
            'idempotency_key': str(uuid.uuid4())
        }, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(res.data['is_guest'])

    def test_spend_threshold_offer_voucher_generation(self):
        """Customer who crosses ₹15,000 threshold earns the ₹50 voucher."""
        self.client.force_authenticate(user=self.worker)
        # Give shop enough stock for high-value sale
        inv1 = Inventory.objects.get(product=self.prod1)
        inv1.current_stock = Decimal('200.00')
        inv1.save()

        # Buy 100 bottles @ 150 = 15,000 + 5% tax = 15,750
        res = self.client.post('/api/sales/checkout/', {
            'shop_id': str(self.shop.id),
            'customer_id': str(self.customer.id),
            'is_guest': False,
            'items': [{'product_id': str(self.prod1.id), 'quantity': '100.00'}],
            'payment_method': 'UPI',
            'idempotency_key': str(uuid.uuid4())
        }, format='json')
        self.assertEqual(res.status_code, 201)

        # Check if voucher was awarded
        vouchers = OfferEligibility.objects.filter(customer=self.customer, offer=self.offer)
        self.assertTrue(vouchers.exists())
        self.assertTrue(vouchers.first().voucher_code.startswith('SB-REWARD-'))

