from decimal import Decimal
from django.test import TestCase
from rest_framework.test import APIClient
from apps.accounts.models import User
from apps.shops.models import Shop
from apps.products.models import Product, Category
from apps.inventory.models import Inventory, StockNotification, LOW_STOCK_THRESHOLD


class LowStockNotificationTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.owner = User.objects.create_user(
            username='owner_inv_test',
            email='owner.inv@smartbazaar.com',
            password='OwnerPassword123!',
            role=User.Role.SHOP_OWNER
        )
        self.shop = Shop.objects.create(
            owner=self.owner,
            name='Alert Test Mart',
            code='SB-ALERT-01',
            phone='9999990000',
            city='Kolkata',
            address='Park Street'
        )
        self.category = Category.objects.create(shop=self.shop, name='Grocery')
        self.product = Product.objects.create(
            shop=self.shop,
            category=self.category,
            name='Tata Salt 1kg',
            sku='SKU-SALT-01',
            selling_price=Decimal('28.00'),
            mrp=Decimal('30.00'),
            unit='PCS'
        )
        self.inv = Inventory.objects.create(
            shop=self.shop,
            product=self.product,
            current_stock=Decimal('20.00')
        )

    def test_automatic_notification_below_15_and_auto_resolve(self):
        """Every product below 15 stock automatically raises an alert and resolves when >= 15."""
        self.assertEqual(LOW_STOCK_THRESHOLD, 15)
        self.assertEqual(StockNotification.objects.filter(is_resolved=False).count(), 0)

        # Drop stock strictly below 15 (14 units)
        self.inv.current_stock = Decimal('14.00')
        self.inv.save()

        res = self.client.get('/api/inventory/low-stock-alerts/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data['count'], 1)
        self.assertEqual(res.data['unread_owner_count'], 1)
        self.assertEqual(res.data['unread_worker_count'], 1)
        self.assertEqual(res.data['alerts'][0]['product_name'], 'Tata Salt 1kg')
        self.assertEqual(res.data['alerts'][0]['severity'], 'WARNING')

        # Drop to 0 -> becomes CRITICAL
        self.inv.current_stock = Decimal('0.00')
        self.inv.save()
        res_zero = self.client.get('/api/inventory/low-stock-alerts/')
        self.assertEqual(res_zero.data['alerts'][0]['severity'], 'CRITICAL')

        # Restock to 15 -> alert automatically resolves
        self.inv.current_stock = Decimal('15.00')
        self.inv.save()
        res_ok = self.client.get('/api/inventory/low-stock-alerts/')
        self.assertEqual(res_ok.data['count'], 0)

