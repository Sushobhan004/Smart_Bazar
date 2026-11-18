import os
import django
from decimal import Decimal
from datetime import timedelta

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'smart_bazaar.settings')
django.setup()

from django.utils import timezone
from apps.accounts.models import User, CustomerProfile
from apps.shops.models import Shop, ShopMembership
from apps.products.models import Category, Product, ProductBarcode
from apps.inventory.models import Inventory, StockTransaction
from apps.customers.models import Offer, CustomerShopAccount

def seed():
    print("Seeding Smart Bazaar demonstration data...")

    # 1. Super Admin
    super_admin, _ = User.objects.get_or_create(
        username='admin',
        defaults={
            'email': 'admin@smartbazaar.com',
            'role': User.Role.SUPER_ADMIN,
            'is_staff': True,
            'is_superuser': True,
            'is_verified': True
        }
    )
    super_admin.set_password('Admin@123')
    super_admin.save()
    print(" Super Admin: admin / Admin@123")

    # 2. Shop Owner
    owner, _ = User.objects.get_or_create(
        username='owner_grocery',
        defaults={
            'email': 'owner@smartbazaar.com',
            'role': User.Role.SHOP_OWNER,
            'is_verified': True
        }
    )
    owner.set_password('Owner@123')
    owner.save()
    print(" Shop Owner: owner_grocery / Owner@123")

    # 3. Shop
    shop, _ = Shop.objects.get_or_create(
        code='SB-SHOP-001',
        defaults={
            'owner': owner,
            'name': 'Smart Bazaar Superstore',
            'category': 'Grocery & FMCG',
            'description': 'One-stop supermarket for daily essentials and premium groceries.',
            'phone': '9830112233',
            'email': 'superstore@smartbazaar.com',
            'address': 'Plot 42, Sector V, Salt Lake City',
            'city': 'Kolkata',
            'state': 'West Bengal',
            'pincode': '700091',
            'gstin': '19AAACB1234F1Z8',
            'status': Shop.Status.APPROVED,
            'upi_vpa': 'smartbazaar@okaxis',
            'upi_name': 'Smart Bazaar Retail',
            'settings': {'return_days': 7, 'loyalty_ratio': 100}
        }
    )
    print(f" Shop: {shop.name} ({shop.code})")

    # 4. Worker / Cashier
    worker, _ = User.objects.get_or_create(
        username='cashier_arun',
        defaults={
            'email': 'arun@smartbazaar.com',
            'phone_number': '9876543210',
            'role': User.Role.WORKER,
            'is_verified': True
        }
    )
    worker.set_password('Worker@123')
    worker.save()

    ShopMembership.objects.get_or_create(
        shop=shop,
        user=worker,
        defaults={
            'role_in_shop': ShopMembership.RoleInShop.CASHIER,
            'can_give_discount': True,
            'max_discount_percent': Decimal('10.00'),
            'can_process_return': True
        }
    )
    print(" Worker: cashier_arun / Worker@123")

    # 5. Customer (Passwordless)
    cust_user, _ = User.objects.get_or_create(
        email='rahul.customer@gmail.com',
        defaults={
            'username': 'rahul_customer',
            'phone_number': '9831098310',
            'role': User.Role.CUSTOMER,
            'is_verified': True
        }
    )
    cust_user.set_unusable_password()
    cust_user.save()

    cust_profile, _ = CustomerProfile.objects.get_or_create(
        user=cust_user,
        defaults={
            'customer_code': 'SB-CUST-774921',
            'full_name': 'Rahul Sharma',
            'phone_number': '9831098310',
            'email': 'rahul.customer@gmail.com',
            'total_spent': Decimal('4250.00'),
            'visit_count': 3,
            'reward_points': 42,
            'registered_at_shop': shop,
            'created_by_worker': worker
        }
    )
    print(f" Customer: {cust_profile.full_name} ({cust_profile.email})")

    # 6. Categories & Products
    cat_grocery, _ = Category.objects.get_or_create(shop=shop, name='Grocery & Staples', defaults={'icon': 'shopping_basket'})
    cat_dairy, _ = Category.objects.get_or_create(shop=shop, name='Dairy & Breakfast', defaults={'icon': 'breakfast_dining'})
    cat_beverage, _ = Category.objects.get_or_create(shop=shop, name='Beverages', defaults={'icon': 'local_drink'})
    cat_snacks, _ = Category.objects.get_or_create(shop=shop, name='Snacks & Biscuits', defaults={'icon': 'fastfood'})

    products_data = [
        ('Aashirvaad Shudh Chakki Atta 5kg', 'SKU-ATT-005', cat_grocery, 'Aashirvaad', Decimal('220.00'), Decimal('255.00'), Decimal('275.00'), Decimal('0.00'), 'PCS', '8901030383700', 45),
        ('Fortune Sunlite Refined Oil 1L', 'SKU-OIL-001', cat_grocery, 'Fortune', Decimal('130.00'), Decimal('149.00'), Decimal('165.00'), Decimal('5.00'), 'PCS', '8906007281234', 60),
        ('Tata Salt Vacuum Evaporated 1kg', 'SKU-SLT-001', cat_grocery, 'Tata', Decimal('22.00'), Decimal('28.00'), Decimal('30.00'), Decimal('0.00'), 'PCS', '8901030383711', 120),
        ('Amul Butter Pasteurized 500g', 'SKU-BTR-500', cat_dairy, 'Amul', Decimal('240.00'), Decimal('275.00'), Decimal('285.00'), Decimal('12.00'), 'PCS', '8901262010054', 30),
        ('Amul Taaza Homogenised Milk 1L', 'SKU-MLK-001', cat_dairy, 'Amul', Decimal('64.00'), Decimal('72.00'), Decimal('75.00'), Decimal('5.00'), 'PCS', '8901262010061', 50),
        ('Nescafe Classic Coffee 100g Jar', 'SKU-NES-100', cat_beverage, 'Nescafe', Decimal('280.00'), Decimal('330.00'), Decimal('350.00'), Decimal('18.00'), 'PCS', '8901058852950', 25),
        ('Red Label Tea 500g', 'SKU-TEA-500', cat_beverage, 'Brooke Bond', Decimal('210.00'), Decimal('260.00'), Decimal('280.00'), Decimal('5.00'), 'PCS', '8901030012345', 40),
        ('Britannia Good Day Butter 200g', 'SKU-GD-200', cat_snacks, 'Britannia', Decimal('35.00'), Decimal('45.00'), Decimal('50.00'), Decimal('18.00'), 'PCS', '8901063012345', 80),
        ('Cadbury Dairy Milk Silk 60g', 'SKU-SLK-060', cat_snacks, 'Cadbury', Decimal('70.00'), Decimal('85.00'), Decimal('90.00'), Decimal('18.00'), 'PCS', '8901233024681', 60),
        ('Maggi 2-Minute Noodles 4-Pack', 'SKU-MAG-004', cat_snacks, 'Nestle', Decimal('50.00'), Decimal('60.00'), Decimal('64.00'), Decimal('12.00'), 'PCS', '8901058852999', 95),
    ]

    for name, sku, cat, brand, cost, sell, mrp, tax, unit, barcode, stock in products_data:
        p, created = Product.objects.get_or_create(
            shop=shop,
            sku=sku,
            defaults={
                'name': name,
                'category': cat,
                'brand': brand,
                'purchase_price': cost,
                'selling_price': sell,
                'mrp': mrp,
                'tax_rate': tax,
                'unit': unit,
                'min_stock_alert': 10,
                'is_active': True
            }
        )
        ProductBarcode.objects.get_or_create(product=p, barcode=barcode, defaults={'is_primary': True})
        inv, _ = Inventory.objects.get_or_create(shop=shop, product=p, defaults={'current_stock': stock, 'reorder_level': 10})
        inv.current_stock = Decimal(str(stock))
        inv.save()

    print(f" Created {len(products_data)} retail products with barcodes & stock.")

    # 7. Promotional Offer
    Offer.objects.get_or_create(
        shop=shop,
        code='FESTIVE50',
        defaults={
            'title': 'Mega ₹50 Voucher on ₹15k Spend',
            'description': 'Spend ₹15,000 or more in cumulative purchases and get an instant ₹50 voucher on your next purchase.',
            'calculation_method': Offer.CalculationMethod.LIFETIME,
            'min_spend_required': Decimal('15000.00'),
            'discount_type': Offer.DiscountType.FLAT,
            'reward_value': Decimal('50.00'),
            'max_discount': Decimal('50.00'),
            'valid_from': timezone.now() - timedelta(days=5),
            'valid_until': timezone.now() + timedelta(days=60),
            'is_active': True
        }
    )
    print(" Configured ₹15,000 spend -> ₹50 reward offer.")
    print("Database seeding completed successfully!")

if __name__ == '__main__':
    seed()

