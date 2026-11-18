# pyright: reportMissingImports=false, reportMissingModuleSource=false, reportGeneralTypeIssues=false
# flake8: noqa
import os
import sys
import re
import json
import secrets
from decimal import Decimal
from pathlib import Path

# Ensure backend root is always present in sys.path
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from django.http import HttpResponse, JsonResponse, FileResponse, Http404
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction
# Direct import resolution for Smart Bazaar modules with universal IDE fallback
try:
    from apps.shops.models import Shop, ShopMembership  # type: ignore # noqa: F401
    from apps.products.models import Product, Category, ProductBarcode  # type: ignore # noqa: F401
    from apps.inventory.models import (  # type: ignore # noqa: F401
        Inventory, StockTransaction, StockNotification,
        LOW_STOCK_THRESHOLD, sync_stock_notification
    )
    from apps.billing.models import Sale, SaleItem, Payment, Invoice  # type: ignore # noqa: F401
    from apps.accounts.models import User, CustomerProfile, OTPVerification  # type: ignore # noqa: F401
except (ImportError, ModuleNotFoundError):
    try:
        from ..shops.models import Shop, ShopMembership  # type: ignore # noqa: F401
        from ..products.models import Product, Category, ProductBarcode  # type: ignore # noqa: F401
        from ..inventory.models import (  # type: ignore # noqa: F401
            Inventory, StockTransaction, StockNotification,
            LOW_STOCK_THRESHOLD, sync_stock_notification
        )
        from ..billing.models import Sale, SaleItem, Payment, Invoice  # type: ignore # noqa: F401
        from ..accounts.models import User, CustomerProfile, OTPVerification  # type: ignore # noqa: F401
    except (ImportError, ModuleNotFoundError, ValueError):
        from backend.apps.shops.models import Shop, ShopMembership  # type: ignore # noqa: F401
        from backend.apps.products.models import Product, Category, ProductBarcode  # type: ignore # noqa: F401
        from backend.apps.inventory.models import (  # type: ignore # noqa: F401
            Inventory, StockTransaction, StockNotification,
            LOW_STOCK_THRESHOLD, sync_stock_notification
        )
        from backend.apps.billing.models import Sale, SaleItem, Payment, Invoice  # type: ignore # noqa: F401
        from backend.apps.accounts.models import User, CustomerProfile, OTPVerification  # type: ignore # noqa: F401

def landing_page(request):
    from .database_provisioner import ensure_all_shop_databases_registered
    from apps.shops.models import ShopDatabaseMapping
    try:
        ensure_all_shop_databases_registered()
    except Exception:
        pass

    shop = Shop.objects.first()
    all_shops = list(Shop.objects.all().select_related('owner'))
    total_shops = len(all_shops)
    total_products = Product.objects.count()
    total_sales_count = Sale.objects.count()
    total_customers = CustomerProfile.objects.count()
    
    # All Shops Data
    shops_data = []
    for s in all_shops:
        owner_name = s.owner.get_full_name() or s.owner.first_name or s.owner.username if s.owner else 'Sushobhan Pratihari'
        owner_phone = (s.owner.phone_number if s.owner else None) or s.phone or '9692276657'
        mapping = getattr(s, 'database_mapping', None) or ShopDatabaseMapping.objects.using('default').filter(shop=s).first()
        db_name = mapping.database_name if mapping else f"SmartBazaar_Shop_{s.code.split('-')[-1] if '-' in s.code else '001'}"
        db_status = mapping.status if mapping else 'ACTIVE'
        shops_data.append({
            'id': str(s.id),
            'name': s.name,
            'code': s.code,
            'city': s.city,
            'address': s.address or f"{s.city}, West Bengal",
            'phone': s.phone or owner_phone,
            'owner_username': s.owner.username if s.owner else 'owner_grocery',
            'owner_name': owner_name,
            'owner_phone': owner_phone,
            'database_name': db_name,
            'db_status': db_status,
            'status': s.status,
            'logo_url': s.logo.url if s.logo else ''
        })

    # Products data (aggregated across default and all active tenant databases)
    products = []
    seen_prod_keys = set()

    def _extract_product_dict(p, fallback_shop_code='SB-SHOP-001'):
        barcode = p.barcodes.first().barcode if hasattr(p, 'barcodes') and p.barcodes.exists() else p.sku
        stock = getattr(p, 'inventory', None)
        current_stock = float(stock.current_stock) if stock else 0.0
        shop_code = (p.shop.code if p.shop else fallback_shop_code) or fallback_shop_code
        return {
            'id': str(p.id),
            'shop_id': str(p.shop_id) if p.shop_id else '',
            'shop_code': shop_code,
            'name': p.name,
            'barcode': barcode or p.sku,
            'selling_price': float(p.selling_price),
            'mrp': float(p.mrp),
            'tax_rate': float(p.tax_rate),
            'unit': p.unit,
            'stock': current_stock,
            'category': p.category.name if p.category else 'General'
        }

    # 1. Load from default database
    for p in Product.objects.using('default').all().select_related('inventory', 'category', 'shop').order_by('-created_at'):
        key = (str(p.id), p.shop.code if p.shop else 'default')
        if key not in seen_prod_keys:
            seen_prod_keys.add(key)
            products.append(_extract_product_dict(p))

    # 2. Load from all registered shop tenant databases
    from django.db import connections
    for alias in list(connections.databases.keys()):
        if alias == 'default':
            continue
        try:
            shop_code_hint = alias.replace('shop_', 'SB-SHOP-').upper()
            for p in Product.objects.using(alias).all().select_related('inventory', 'category', 'shop'):
                key = (str(p.id), p.shop.code if p.shop else shop_code_hint)
                if key not in seen_prod_keys:
                    seen_prod_keys.add(key)
                    products.append(_extract_product_dict(p, fallback_shop_code=shop_code_hint))
        except Exception:
            pass

    # Workers data - include all registered workers for the stores
    workers = []
    worker_users = User.objects.filter(role=User.Role.WORKER).order_by('-date_joined')
    emp_idx = 1
    for u in worker_users:
        m = ShopMembership.objects.filter(user=u).select_related('shop').first()
        emp_code = f"SB-EMP-{emp_idx:03d}"
        emp_idx += 1
        workers.append({
            'user_id': str(u.id),
            'employee_id': emp_code,
            'worker_id': u.username,
            'name': u.get_full_name() or u.first_name or u.username,
            'phone': u.phone_number or 'N/A',
            'email': u.email,
            'role': m.role_in_shop if m else 'CASHIER',
            'shop_id': str(m.shop.id) if m and m.shop else '',
            'shop_code': m.shop.code if m and m.shop else 'SB-SHOP-001',
            'shop_name': m.shop.name if m and m.shop else 'Smart Bazaar Superstore',
            'is_active': u.is_active and (m.is_active if m else True),
            'password': 'CashierPass@123',
            'joined': u.date_joined.strftime('%d %b %Y') if u.date_joined else 'Recent'
        })
    if not workers:
        workers = [{
            'user_id': 'demo-worker-1',
            'employee_id': 'SB-EMP-001',
            'worker_id': 'cashier_arun',
            'name': 'Arun Kumar',
            'phone': '9876543210',
            'email': 'arun@smartbazaar.com',
            'role': 'CASHIER',
            'shop_id': 'default-shop-1',
            'shop_code': 'SB-SHOP-001',
            'shop_name': 'Smart Bazaar Superstore',
            'is_active': True,
            'password': 'CashierPass@123',
            'joined': '10 Nov 2026'
        }]

    # Recent sales
    recent_sales = []
    for s in Sale.objects.all().select_related('shop', 'worker', 'customer').order_by('-created_at')[:10]:
        cashier_title = s.worker.get_full_name() or s.worker.first_name or s.worker.username if s.worker else 'Arun Kumar'
        cust_title = s.customer.full_name if s.customer else (s.guest_name or 'Walk-in Customer')
        cust_mob = s.customer.phone_number if s.customer else (s.guest_phone or 'N/A')
        recent_sales.append({
            'bill_number': s.bill_number,
            'shop_name': s.shop.name if s.shop else 'Smart Bazaar Superstore',
            'shop_code': s.shop.code if s.shop else 'SB-SHOP-001',
            'cashier_name': cashier_title,
            'cashier_id': s.worker.username if s.worker else 'cashier_arun',
            'customer_name': cust_title,
            'customer_phone': cust_mob,
            'final_total': float(s.final_total),
            'payment_method': s.payment_method,
            'created_at': s.created_at.strftime('%d %b, %H:%M')
        })

    shop_logo_url = shop.logo.url if (shop and shop.logo) else ''
    shop_logo_style = 'display: block;' if shop_logo_url else 'display: none;'
    shop_placeholder_style = 'display: none;' if shop_logo_url else 'display: inline;'
    
    owner_user = shop.owner if (shop and shop.owner) else User.objects.filter(role=User.Role.SHOP_OWNER).first()
    owner_name = owner_user.get_full_name() or owner_user.first_name if owner_user else 'Sushobhan Pratihari'
    owner_phone = owner_user.phone_number if owner_user else '9692276657'

    shop_mapping = getattr(shop, 'database_mapping', None) if shop else None
    if not shop_mapping and shop:
        shop_mapping = ShopDatabaseMapping.objects.using('default').filter(shop=shop).first()
    db_name = shop_mapping.database_name if shop_mapping else 'SmartBazaar_Shop_001'

    shop_info = {
        'name': shop.name if shop else 'Smart Bazaar Superstore',
        'code': shop.code if shop else 'SB-SHOP-001',
        'city': shop.city if shop else 'Kolkata',
        'address': (shop.address if shop else 'Station Road, Kolkata - 700001'),
        'phone': shop.phone if shop else '+91 96922 76657',
        'upi_vpa': shop.upi_vpa if shop else 'smartbazaar@okaxis',
        'owner_name': owner_name,
        'owner_phone': owner_phone,
        'database_name': db_name,
        'db_status': 'ACTIVE'
    }

    # Shop Owners list for Super Admin
    shop_owners = []
    owner_idx = 1
    for owner in User.objects.filter(role=User.Role.SHOP_OWNER).order_by('-date_joined'):
        shops_list = list(owner.owned_shops.values('name', 'code', 'city', 'address', 'phone', 'status'))
        shop_primary = shops_list[0] if shops_list else {
            'name': 'Smart Bazaar Branch A',
            'code': f'SB-SHOP-{owner_idx:03d}',
            'city': 'Kolkata',
            'address': 'Station Road, Kolkata - 700001',
            'phone': owner.phone_number or '9830112231',
            'status': 'APPROVED'
        }
        code = shop_primary.get('code', f'SB-SHOP-{owner_idx:03d}')
        mapping = ShopDatabaseMapping.objects.using('default').filter(shop_id_code=code).first()
        db_name = mapping.database_name if mapping else f"SmartBazaar_Shop_{code.split('-')[-1] if '-' in code else f'{owner_idx:03d}'}"
        db_status = mapping.status if mapping else 'ACTIVE'
        shop_owners.append({
            'user_id': str(owner.id),
            'owner_id': f"SB-OWNER-{code.split('-')[-1] if '-' in code else f'{owner_idx:03d}'}",
            'username': owner.username,
            'login_id': owner.username,
            'name': owner.get_full_name() or owner.first_name or owner.username,
            'phone': owner.phone_number or shop_primary.get('phone', '9830112231'),
            'email': owner.email,
            'shop_name': shop_primary.get('name', f'Smart Bazaar Branch {owner_idx}'),
            'shop_code': code,
            'database_name': db_name,
            'db_status': db_status,
            'city': shop_primary.get('city', 'Kolkata'),
            'address': shop_primary.get('address', 'Station Road, Kolkata - 700001'),
            'is_verified': owner.is_verified,
            'is_active': owner.is_active,
            'status': shop_primary.get('status', 'APPROVED'),
            'password': 'OwnerPass@123',
            'joined': owner.date_joined.strftime('%d %b %Y') if owner.date_joined else '11 Nov 2026'
        })
        owner_idx += 1

    if not shop_owners:
        shop_owners.append({
            'user_id': 'default-owner-1',
            'owner_id': 'SB-OWNER-001',
            'username': 'owner_grocery',
            'name': 'Sushobhan Pratihari',
            'phone': '9692276657',
            'email': 'owner@smartbazaar.com',
            'shop_name': 'Smart Bazaar Superstore',
            'shop_code': 'SB-SHOP-001',
            'city': 'Kolkata',
            'address': 'Station Road, Kolkata - 700001',
            'is_verified': True,
            'is_active': True,
            'status': 'APPROVED',
            'password': 'OwnerPass@123',
            'joined': '11 Nov 2026'
        })

    # Customers directory data - partitioned by registered shop
    customers_list = []
    for c in CustomerProfile.objects.using('default').select_related('registered_at_shop', 'created_by_worker').order_by('-created_at'):
        reg_shop = c.registered_at_shop
        reg_worker = c.created_by_worker
        worker_label = (reg_worker.get_full_name() or reg_worker.username) if reg_worker else 'Cashier / POS Staff'
        customers_list.append({
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

    products_json = json.dumps(products)
    workers_json = json.dumps(workers)
    recent_sales_json = json.dumps(recent_sales)
    shop_info_json = json.dumps(shop_info)
    shop_owners_json = json.dumps(shop_owners)
    shops_json = json.dumps(shops_data)
    customers_json = json.dumps(customers_list)


    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=5.0, viewport-fit=cover">
    <meta name="theme-color" content="#0F5132">
    <meta name="mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-capable" content="yes">
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    <link rel="manifest" href="/manifest.json">
    <title>Smart Bazaar — Supermarket Mobile POS & Multi-Branch Portal</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {{
            /* Premium Supermarket Forest Green Palette */
            --primary: #0F5132;         /* Dark green primary */
            --primary-dark: #0A3622;    /* Deep forest dark green */
            --primary-light: #166534;   /* Classic rich green */
            --secondary: #15803D;       /* Forest emerald accent */
            --accent: #22C55E;          /* Bright vibrant green */
            --accent-soft: #DCFCE7;     /* Soft mint green */
            --accent-mint: #F0FDF4;     /* Lightest mint */
            --bg: #F8FAFC;              /* Clean soft neutral background */
            --card: #FFFFFF;            /* Pure white card */
            --text-main: #0F172A;       /* Ultra dark readable slate */
            --text-muted: #64748B;      /* Slate muted */
            --text-subtle: #94A3B8;     /* Subtle text */
            --success: #15803D;         /* Success green */
            --success-soft: #DCFCE7;
            --warning: #D97706;         /* Warning amber */
            --warning-soft: #FEF3C7;
            --danger: #DC2626;          /* Danger red */
            --danger-soft: #FEE2E2;
            --border: #E2E8F0;          /* Clean light border */
            --border-hover: #CBD5E1;
            --radius-sm: 8px;
            --radius-md: 12px;
            --radius-lg: 16px;
            --radius-xl: 20px;
            --radius-full: 9999px;
            --shadow-sm: 0 1px 3px rgba(0,0,0,0.05);
            --shadow-md: 0 4px 16px -2px rgba(15, 81, 50, 0.08), 0 2px 6px -1px rgba(0,0,0,0.04);
            --shadow-lg: 0 12px 30px -4px rgba(15, 81, 50, 0.14), 0 4px 10px -2px rgba(0,0,0,0.05);
            --shadow-green: 0 4px 14px rgba(15, 81, 50, 0.28);
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        html {{
            -webkit-text-size-adjust: 100%;
            scroll-behavior: smooth;
            overflow-x: hidden !important;
            width: 100% !important;
            max-width: 100% !important;
            box-sizing: border-box !important;
        }}
        body {{
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background-color: var(--bg);
            color: var(--text-main);
            min-height: 100vh;
            width: 100% !important;
            max-width: 100% !important;
            overflow-x: hidden !important;
            position: relative;
            box-sizing: border-box !important;
            display: flex;
            flex-direction: column;
            line-height: 1.5;
            -webkit-font-smoothing: antialiased;
        }}

        /* Subtle sleek scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: transparent; }}
        ::-webkit-scrollbar-thumb {{ background: #CBD5E1; border-radius: 999px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #94A3B8; }}

        /* Responsive Sticky Header */
        header.app-header {{
            background: #0F5132;
            color: white;
            padding: 0.65rem 1rem;
            box-shadow: 0 2px 12px rgba(10, 54, 34, 0.22);
            border-bottom: 1px solid rgba(255, 255, 255, 0.12);
            position: sticky;
            top: 0;
            z-index: 100;
            backdrop-filter: blur(8px);
            width: 100%;
            max-width: 100%;
            min-width: 0;
            box-sizing: border-box;
        }}
        .header-inner {{
            width: 100%;
            max-width: 1240px;
            margin: 0 auto;
            display: flex;
            flex-direction: column;
            gap: 6px;
            box-sizing: border-box;
        }}
        .header-main-row {{
            display: flex;
            align-items: center;
            justify-content: space-between;
            width: 100%;
            gap: 10px;
            box-sizing: border-box;
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: clamp(1.1rem, 3.5vw, 1.35rem);
            font-weight: 800;
            letter-spacing: -0.5px;
            user-select: none;
            min-width: 0;
            color: white;
        }}
        .brand-icon {{
            background: rgba(255, 255, 255, 0.2);
            width: 34px;
            height: 34px;
            border-radius: 9px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.15rem;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.3);
            flex-shrink: 0;
        }}
        .header-right-slot {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
        }}
        .header-badge-row {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
            width: 100%;
            padding-top: 2px;
            box-sizing: border-box;
        }}
        .header-role-pill {{
            font-size: 0.74rem !important;
            padding: 3px 8px !important;
            white-space: nowrap;
        }}
        .header-user-pill {{
            font-weight: 700;
            font-size: 0.8rem;
            color: #DCFCE7;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
            max-width: 220px;
        }}
        .mobile-only-right {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-shrink: 0;
        }}
        .desktop-only-logout {{
            display: none !important;
        }}
        @media (min-width: 769px) {{
            .mobile-only-right {{
                display: none !important;
            }}
            .desktop-only-logout {{
                display: inline-flex !important;
            }}
        }}

        @media (min-width: 769px) {{
            header.app-header {{
                padding: 0.85rem 1.5rem;
            }}
            .header-inner {{
                flex-direction: row;
                justify-content: space-between;
                align-items: center;
                gap: 16px;
            }}
            .header-main-row {{
                width: auto;
            }}
            .header-badge-row {{
                width: auto;
                padding-top: 0;
                justify-content: flex-end;
            }}
        }}

        /* Universal Responsive Hero Card (Super Admin, Shop Owner, POS) */
        .dashboard-hero-card {{
            background: #FFFFFF;
            border-radius: 14px;
            border: 1.5px solid #E2E8F0;
            box-shadow: 0 4px 14px rgba(15, 81, 50, 0.06);
            padding: 16px 16px;
            margin-bottom: 20px;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            overflow: hidden !important;
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .hero-identity {{
            display: flex;
            align-items: flex-start;
            gap: 12px;
            flex: 1 1 260px;
            min-width: 0 !important;
            max-width: 100% !important;
            box-sizing: border-box;
        }}
        .hero-icon-box {{
            width: 46px;
            height: 46px;
            border-radius: 12px;
            background: #F0FDF4;
            border: 2px solid var(--primary);
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.55rem;
            box-shadow: 0 3px 10px rgba(15, 81, 50, 0.1);
            flex-shrink: 0;
        }}
        .hero-text-block {{
            flex: 1 1 0;
            min-width: 0 !important;
            max-width: 100% !important;
            overflow-wrap: break-word !important;
            word-break: normal !important;
            box-sizing: border-box;
        }}
        .hero-badge-wrap {{
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
            margin-bottom: 4px;
            min-width: 0;
        }}
        .hero-meta-label {{
            font-size: 0.76rem;
            color: #0F5132;
            font-weight: 700;
            overflow-wrap: break-word;
            word-break: normal;
        }}
        .hero-title {{
            font-size: clamp(1.10rem, 3.8vw, 1.45rem) !important;
            font-weight: 800;
            color: var(--primary);
            margin: 2px 0 3px 0;
            line-height: 1.25;
            overflow-wrap: break-word !important;
            word-break: normal !important;
        }}
        .hero-desc {{
            color: var(--text-muted);
            font-size: 0.81rem;
            margin: 0;
            line-height: 1.4;
            overflow-wrap: break-word !important;
            word-break: normal !important;
        }}
        .hero-actions {{
            display: flex;
            align-items: center;
            gap: 8px;
            flex-wrap: wrap;
            width: 100%;
            box-sizing: border-box;
        }}
        @media (max-width: 640px) {{
            .dashboard-hero-card {{
                padding: 14px 12px !important;
                gap: 12px !important;
            }}
            .hero-identity {{
                width: 100% !important;
                max-width: 100% !important;
                min-width: 0 !important;
                gap: 10px !important;
            }}
            .hero-text-block {{
                width: 100% !important;
                min-width: 0 !important;
            }}
            .hero-badge-wrap {{
                flex-direction: column !important;
                align-items: flex-start !important;
                gap: 2px !important;
            }}
            .hero-meta-label {{
                display: block !important;
                width: 100% !important;
                font-size: 0.74rem !important;
            }}
            .hero-title {{
                font-size: 1.15rem !important;
                line-height: 1.25 !important;
                margin: 2px 0 3px 0 !important;
                word-break: normal !important;
                overflow-wrap: break-word !important;
            }}
            .hero-actions {{
                display: flex !important;
                flex-direction: column !important;
                align-items: stretch !important;
                width: 100% !important;
                gap: 8px !important;
            }}
            .hero-action-btn, .hero-status-badge {{
                width: 100% !important;
                flex: 1 1 100% !important;
                text-align: center !important;
                justify-content: center !important;
                box-sizing: border-box !important;
                display: flex !important;
                align-items: center !important;
                min-height: 40px !important;
            }}
        }}
        @media (min-width: 769px) {{
            .hero-actions {{
                width: auto;
            }}
            .dashboard-hero-card {{
                padding: 18px 22px;
            }}
        }}
        .hero-action-btn {{
            border-color: var(--primary);
            color: var(--primary);
            font-weight: 700;
            background: #F0FDF4;
            padding: 7px 12px;
            font-size: 0.78rem;
            flex: 1 1 auto;
            justify-content: center;
            box-sizing: border-box;
            min-height: 40px;
        }}
        @media (min-width: 769px) {{
            .hero-action-btn {{
                flex: 0 0 auto;
            }}
        }}
        .hero-status-badge {{
            font-size: 0.78rem;
            padding: 6px 12px;
            flex: 1 1 auto;
            justify-content: center;
            text-align: center;
            box-sizing: border-box;
            min-height: 40px;
        }}
        @media (min-width: 769px) {{
            .hero-status-badge {{
                flex: 0 0 auto;
            }}
        }}
        .brand {{
            display: flex;
            align-items: center;
            gap: 12px;
            font-size: 1.35rem;
            font-weight: 800;
            letter-spacing: -0.5px;
            user-select: none;
        }}
        .brand-icon {{
            background: rgba(255, 255, 255, 0.2);
            width: 38px;
            height: 38px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.25rem;
            box-shadow: inset 0 0 0 1px rgba(255,255,255,0.3);
        }}
        .header-actions {{
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .badge-status {{
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: rgba(255, 255, 255, 0.16);
            padding: 6px 14px;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 600;
            border: 1px solid rgba(255,255,255,0.2);
        }}
        .pulse {{
            width: 8px;
            height: 8px;
            background: #22c55e;
            border-radius: 50%;
            box-shadow: 0 0 0 rgba(34, 197, 94, 0.7);
            animation: pulse 2s infinite;
        }}
        @keyframes pulse {{
            0% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }}
            70% {{ box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }}
            100% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }}
        }}
        
        main {{
            max-width: 1240px;
            width: 100%;
            margin: 22px auto 40px;
            padding: 0 1.25rem;
            flex: 1;
            min-width: 0;
            box-sizing: border-box;
        }}

        /* Cards & Surfaces */
        .card {{
            background: var(--card);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: var(--shadow-md);
            border: 1px solid var(--border);
            margin-bottom: 22px;
            transition: box-shadow 0.2s ease, transform 0.2s ease;
            width: 100%;
            max-width: 100%;
            min-width: 0;
            box-sizing: border-box;
            overflow: hidden;
        }}

        /* Buttons & Touch Targets */
        .btn {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            background: var(--primary);
            color: white;
            text-decoration: none;
            padding: 9px 16px;
            border-radius: 10px;
            font-weight: 700;
            font-size: 0.88rem;
            border: none;
            cursor: pointer;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            user-select: none;
            touch-action: manipulation;
        }}
        .btn:hover {{
            background: var(--primary-dark);
            transform: translateY(-1.5px);
            box-shadow: 0 4px 14px rgba(15, 81, 50, 0.25);
        }}
        .btn:active {{
            transform: scale(0.97);
        }}
        .btn-outline {{
            background: transparent;
            color: var(--primary);
            border: 1.5px solid var(--primary);
        }}
        .btn-outline:hover {{
            background: var(--accent-soft);
            color: var(--primary-dark);
        }}
        .btn-sm {{ padding: 5px 10px; font-size: 0.78rem; border-radius: 7px; }}
        .btn-danger {{ background: var(--danger); }}
        .btn-danger:hover {{ background: #B91C1C; box-shadow: 0 4px 14px rgba(220, 38, 38, 0.25); }}
        .btn-success {{ background: var(--success); }}
        .btn-success:hover {{ background: #15803D; box-shadow: 0 4px 14px rgba(22, 163, 74, 0.25); }}
        .btn-warning {{ background: var(--warning); color: #78350F; }}

        /* Auth Container & Tabs */
        .auth-container {{
            max-width: 460px;
            margin: 28px auto;
            padding: 32px 28px;
            border-radius: 18px;
            box-shadow: 0 10px 30px rgba(15, 81, 50, 0.08), 0 2px 8px rgba(0, 0, 0, 0.04);
            border: 1px solid #E2E8F0;
            background: #FFFFFF;
        }}
        .nav-tabs {{
            display: flex;
            background: #DCFCE7;
            padding: 4px;
            border-radius: 12px;
            margin-bottom: 20px;
            gap: 4px;
        }}
        .nav-tab {{
            flex: 1;
            text-align: center;
            padding: 10px 14px;
            border-radius: 10px;
            cursor: pointer;
            font-weight: 700;
            font-size: 0.9rem;
            color: var(--primary);
            transition: 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            user-select: none;
        }}
        .nav-tab.active {{
            background: white;
            color: var(--primary);
            box-shadow: 0 2px 10px rgba(15, 81, 50, 0.15);
        }}

        /* Form elements */
        .form-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 14px;
            margin-bottom: 16px;
        }}
        .form-group {{
            margin-bottom: 12px;
        }}
        .form-group label {{
            display: block;
            font-size: 0.8rem;
            font-weight: 700;
            margin-bottom: 6px;
            color: #334155;
            text-transform: uppercase;
            letter-spacing: 0.4px;
        }}
        .form-control {{
            width: 100%;
            padding: 10px 14px;
            border-radius: 10px;
            border: 1.5px solid var(--border);
            font-size: 0.92rem;
            outline: none;
            transition: border-color 0.2s, box-shadow 0.2s;
            font-family: inherit;
            background: white;
        }}
        .form-control:focus {{
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(15, 81, 50, 0.15);
        }}

        /* Responsive Data Tables */
        .table-responsive {{
            width: 100%;
            overflow-x: auto;
            -webkit-overflow-scrolling: touch;
            border-radius: 12px;
            border: 1px solid var(--border);
            margin-bottom: 10px;
            background: white;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.88rem;
            white-space: normal;
        }}
        .data-table th, .data-table td {{
            padding: 12px 14px;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        .data-table th {{
            background: #F8FAFC;
            color: var(--text-muted);
            font-size: 0.74rem;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.4px;
            position: sticky;
            top: 0;
            z-index: 2;
        }}
        .data-table tbody tr:hover {{
            background-color: #FBFBFE;
        }}

        /* Badges - Green & Forest Accents */
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            border-radius: 999px;
            font-size: 0.75rem;
            font-weight: 700;
            letter-spacing: 0.2px;
            white-space: nowrap;
        }}
        .badge-purple {{ background: #DCFCE7; color: #0F5132; border: 1px solid #BBF7D0; }}
        .badge-blue {{ background: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD; }}
        .badge-green {{ background: #DCFCE7; color: #15803D; border: 1px solid #86EFAC; }}
        .badge-amber {{ background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A; }}
        .badge-red {{ background: #FEE2E2; color: #B91C1C; border: 1px solid #FECACA; }}

        /* Mobile-First Bottom Navigation Bar */
        .mobile-bottom-nav {{
            display: none;
            position: fixed;
            bottom: 0;
            left: 0;
            right: 0;
            background: #FFFFFF;
            border-top: 1px solid #E2E8F0;
            box-shadow: 0 -4px 20px rgba(0, 0, 0, 0.08);
            z-index: 999;
            padding: 6px 8px calc(6px + env(safe-area-inset-bottom, 12px));
            justify-content: space-around;
            align-items: center;
            backdrop-filter: blur(12px);
        }}
        .bottom-nav-item {{
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 3px;
            color: #64748B;
            text-decoration: none;
            font-size: 0.68rem;
            font-weight: 700;
            padding: 6px 10px;
            border-radius: 12px;
            transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
            min-width: 56px;
            min-height: 48px;
            border: none;
            background: transparent;
            cursor: pointer;
            user-select: none;
            touch-action: manipulation;
            position: relative;
        }}
        .bottom-nav-item .nav-icon {{
            font-size: 1.25rem;
            line-height: 1;
            transition: transform 0.2s cubic-bezier(0.34, 1.56, 0.64, 1);
        }}
        .bottom-nav-item.active {{
            color: #0F5132;
            background: #DCFCE7;
        }}
        .bottom-nav-item.active .nav-icon {{
            transform: scale(1.15);
        }}
        .bottom-nav-item:active {{
            transform: scale(0.92);
        }}
        .bottom-nav-badge {{
            position: absolute;
            top: 2px;
            right: 8px;
            background: #DC2626;
            color: white;
            font-size: 0.62rem;
            font-weight: 800;
            padding: 1px 6px;
            border-radius: 999px;
            line-height: 1.3;
        }}

        /* Mobile Cart Bottom Sheet Drawer */
        .mobile-cart-drawer {{
            display: none;
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(0,0,0,0.65);
            z-index: 10000;
            justify-content: flex-end;
            flex-direction: column;
            backdrop-filter: blur(4px);
        }}
        .mobile-cart-sheet {{
            background: #FFFFFF;
            border-radius: 24px 24px 0 0;
            max-height: 88vh;
            overflow-y: auto;
            padding: 18px 18px calc(24px + env(safe-area-inset-bottom, 16px));
            box-shadow: 0 -10px 40px rgba(0,0,0,0.25);
            animation: sheetSlideUp 0.25s cubic-bezier(0.16, 1, 0.3, 1);
        }}
        @keyframes sheetSlideUp {{
            from {{ transform: translateY(100%); }}
            to {{ transform: translateY(0); }}
        }}
        .drawer-pill-handle {{
            width: 48px;
            height: 5px;
            background: #CBD5E1;
            border-radius: 999px;
            margin: 0 auto 16px;
        }}

        /* POS Category Filter Chips */
        .pos-category-chips {{
            display: flex;
            gap: 8px;
            overflow-x: auto;
            padding: 4px 2px 12px;
            scrollbar-width: none;
            -ms-overflow-style: none;
            user-select: none;
            -webkit-overflow-scrolling: touch;
        }}
        .pos-category-chips::-webkit-scrollbar {{
            display: none;
        }}
        .pos-chip {{
            padding: 8px 16px;
            background: #FFFFFF;
            color: #475569;
            border-radius: 999px;
            font-size: 0.82rem;
            font-weight: 700;
            white-space: nowrap;
            cursor: pointer;
            transition: all 0.2s ease;
            border: 1px solid #E2E8F0;
            touch-action: manipulation;
            box-shadow: 0 1px 3px rgba(0,0,0,0.03);
        }}
        .pos-chip.active {{
            background: #0F5132;
            color: white;
            border-color: #0F5132;
            box-shadow: 0 3px 10px rgba(15, 81, 50, 0.28);
        }}

        /* Mobile Action Cards (One-Handed Operation) */
        .mobile-action-card {{
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 14px;
            padding: 14px;
            display: flex;
            align-items: center;
            gap: 12px;
            cursor: pointer;
            transition: all 0.2s ease;
            touch-action: manipulation;
            box-shadow: 0 1px 3px rgba(0,0,0,0.04);
            user-select: none;
        }}
        .mobile-action-card:hover, .mobile-action-card:active {{
            border-color: #86EFAC;
            background: #F0FDF4;
            transform: translateY(-1.5px);
        }}
        .action-icon-circle {{
            width: 44px;
            height: 44px;
            border-radius: 12px;
            background: #DCFCE7;
            color: #0F5132;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.35rem;
            flex-shrink: 0;
        }}

        .view-section {{ display: none; }}
        .view-section.active {{ display: block; animation: fadeIn 0.3s ease; }}
        @keyframes fadeIn {{ from {{ opacity: 0; transform: translateY(6px); }} to {{ opacity: 1; transform: translateY(0); }} }}

        /* Fully Responsive KPI Dashboard Grid (1-col mobile, 2-col phablet, 3-col tablet, 4+ desktop) */
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-bottom: 20px;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
        }}
        @media (max-width: 480px) {{
            /* 1 column on small phones under 480px so all labels fit 100% comfortably without clipping */
            .kpi-grid {{
                grid-template-columns: 1fr !important;
                gap: 10px !important;
            }}
        }}
        @media (min-width: 481px) and (max-width: 768px) {{
            /* 2 columns on wider mobile devices */
            .kpi-grid {{
                grid-template-columns: repeat(2, 1fr) !important;
                gap: 12px !important;
            }}
        }}
        @media (min-width: 769px) and (max-width: 1024px) {{
            /* 3 columns on tablet */
            .kpi-grid {{
                grid-template-columns: repeat(3, 1fr) !important;
                gap: 14px !important;
            }}
        }}
        @media (min-width: 1025px) {{
            /* Multi-column on desktop */
            .kpi-grid {{
                grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
                gap: 14px;
            }}
        }}

        .kpi-card {{
            background: white;
            border-radius: 14px;
            padding: 14px 16px !important;
            border: 1px solid var(--border);
            display: flex;
            flex-direction: column;
            gap: 4px;
            position: relative;
            overflow: hidden;
            box-shadow: var(--shadow-sm);
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
            overflow-wrap: break-word !important;
            word-break: break-word !important;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .kpi-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--primary), var(--accent));
        }}
        .kpi-card:hover {{
            transform: translateY(-2px);
            box-shadow: var(--shadow-md);
        }}
        .kpi-title {{
            font-size: 0.74rem !important;
            color: var(--text-muted);
            font-weight: 700;
            text-transform: uppercase;
            letter-spacing: 0.3px;
            line-height: 1.3;
            overflow-wrap: break-word !important;
            word-break: break-word !important;
        }}
        .kpi-value {{
            font-size: clamp(1.35rem, 4.5vw, 1.85rem) !important;
            font-weight: 800;
            color: var(--primary);
            letter-spacing: -0.5px;
            line-height: 1.2;
            margin-top: 2px;
        }}

        /* Universal Responsive Table & Form Guards */
        .table-responsive {{
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch !important;
            display: block !important;
            box-sizing: border-box !important;
        }}
        .data-table {{
            width: 100% !important;
            border-collapse: collapse;
        }}
        .form-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
            gap: 12px;
            width: 100% !important;
            max-width: 100% !important;
            min-width: 0 !important;
            box-sizing: border-box !important;
        }}
        @media (max-width: 640px) {{
            .form-grid {{
                grid-template-columns: 1fr !important;
            }}
        }}

        /* POS styles */
        .pos-grid {{
            display: grid;
            grid-template-columns: 1.6fr 1.05fr;
            gap: 20px;
            align-items: start;
        }}
        .pos-cart-sticky {{
            background: #F8FAFC;
            border: 1.5px solid var(--border);
            border-radius: 14px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            position: sticky;
            top: 85px;
            box-shadow: var(--shadow-sm);
        }}
        .product-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
            gap: 12px;
            max-height: 560px;
            overflow-y: auto;
            padding-right: 6px;
            -webkit-overflow-scrolling: touch;
        }}
        .product-item {{
            background: white;
            border: 1.5px solid var(--border);
            border-radius: 12px;
            padding: 12px 14px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            cursor: pointer;
            transition: all 0.18s ease;
            box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            user-select: none;
            touch-action: manipulation;
        }}
        .product-item:hover {{
            border-color: var(--primary);
            box-shadow: 0 6px 18px rgba(15, 81, 50, 0.12);
            transform: translateY(-2px);
        }}
        .product-item:active {{
            transform: scale(0.98);
        }}
        .cart-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
            margin-bottom: 12px;
        }}
        .cart-table th, .cart-table td {{
            padding: 8px 6px;
            border-bottom: 1px solid var(--border);
        }}
        .receipt-container {{
            background: #FFFFF0;
            border: 1px dashed #78716C;
            font-family: 'JetBrains Mono', monospace;
            padding: 18px;
            width: 320px;
            margin: 0 auto;
            font-size: 0.82rem;
            box-shadow: 0 4px 20px rgba(0,0,0,0.1);
            color: #1C1917;
            line-height: 1.4;
        }}

        /* Swipeable Barcode Chip Row */
        .quick-barcodes-scroll {{
            display: flex;
            align-items: center;
            gap: 6px;
            overflow-x: auto;
            white-space: nowrap;
            -webkit-overflow-scrolling: touch;
            padding: 4px 0;
            scrollbar-width: none;
        }}
        .quick-barcodes-scroll::-webkit-scrollbar {{ display: none; }}

        /* Mobile Sticky Floating Cart Bar */
        .mobile-cart-float {{
            position: fixed;
            bottom: 16px;
            left: 16px;
            right: 16px;
            z-index: 999;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            padding: 12px 18px;
            border-radius: 14px;
            box-shadow: 0 10px 30px rgba(15, 81, 50, 0.35);
            display: flex;
            align-items: center;
            justify-content: space-between;
            cursor: pointer;
            animation: slideUp 0.3s ease;
        }}
        @keyframes slideUp {{
            from {{ transform: translateY(100%); opacity: 0; }}
            to {{ transform: translateY(0); opacity: 1; }}
        }}

        /* ============================================================== */
        /* RESPONSIVE MEDIA QUERIES FOR EVERY DEVICE (Mobile, Tablet, Desktop) */
        /* ============================================================== */

        /* Tablets & Medium Screens (< 992px) */
        @media (max-width: 991px) {{
            header {{ padding: 0.9rem 1.25rem; }}
            .pos-grid {{
                grid-template-columns: 1fr;
            }}
            .pos-cart-sticky {{
                position: static;
                top: auto;
            }}
            .product-grid {{
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                max-height: 480px;
            }}
            .kpi-grid {{
                grid-template-columns: repeat(2, 1fr);
            }}
        }}

        /* Mobile Phones (< 768px) - Full Mobile-First Experience */
        @media (max-width: 768px) {{
            .mobile-bottom-nav {{
                display: flex !important;
            }}
            body {{ font-size: 14px; }}
            main {{
                padding: 0 10px !important;
                margin: 10px auto !important;
                padding-bottom: calc(80px + env(safe-area-inset-bottom, 16px)) !important;
            }}
            header.app-header {{
                display: block !important;
                padding: 0.65rem 0.85rem !important;
                width: 100% !important;
                max-width: 100% !important;
                box-sizing: border-box !important;
            }}
            .brand {{
                font-size: 1.15rem;
                gap: 8px;
            }}
            .brand-icon {{
                width: 32px;
                height: 32px;
                font-size: 1.05rem;
            }}
            .header-actions {{
                font-size: 0.78rem;
                gap: 6px;
            }}
            .badge-status {{
                padding: 4px 10px;
                font-size: 0.75rem;
            }}
            main {{
                padding: 0 10px;
                margin: 12px auto 60px;
            }}
            .card {{
                padding: 1.1rem;
                border-radius: 14px;
                margin-bottom: 16px;
            }}
            .auth-container {{
                padding: 22px 16px;
                margin: 14px auto;
            }}
            .nav-tabs {{
                margin-bottom: 14px;
            }}
            .nav-tab {{
                padding: 8px 10px;
                font-size: 0.82rem;
            }}
            .form-grid {{
                grid-template-columns: 1fr;
                gap: 10px;
            }}
            .form-control {{
                padding: 9px 12px;
                font-size: 0.88rem;
            }}
            .btn {{
                padding: 8px 14px;
                font-size: 0.82rem;
            }}

            /* Product Grid: 2 clean cards per row on mobile phones */
            .product-grid {{
                grid-template-columns: repeat(2, 1fr);
                gap: 9px;
                max-height: 440px;
                padding-right: 2px;
            }}
            .product-item {{
                padding: 10px;
            }}
            .product-item .product-title {{
                font-size: 0.84rem;
                min-height: 32px;
            }}

            /* Admin Section - 1 col on <= 540px, 2 col on 541-768px */
            .kpi-grid {{
                grid-template-columns: repeat(2, 1fr);
                gap: 10px;
            }}
            @media (max-width: 540px) {{
                .kpi-grid {{
                    grid-template-columns: 1fr !important;
                    gap: 10px !important;
                }}
            }}
            .kpi-card {{
                padding: 1rem;
            }}
            .kpi-value {{
                font-size: 1.4rem;
            }}

            /* Tables Mobile */
            .data-table th, .data-table td {{
                padding: 9px 10px;
                font-size: 0.8rem;
            }}

            /* Scanner Box Input stack */
            .scanner-input-group {{
                flex-direction: column !important;
                align-items: stretch !important;
            }}
            .scanner-input-group .btn, .scanner-input-group input {{
                width: 100% !important;
            }}
        }}

        /* Very Small Screens (< 420px) */
        @media (max-width: 419px) {{
            .product-grid {{
                grid-template-columns: repeat(2, 1fr);
                gap: 6px;
            }}
            .product-item {{
                padding: 8px;
            }}
            .product-item strong {{
                font-size: 0.95rem;
            }}
            .kpi-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <header class="app-header">
        <div class="header-inner">
            <div class="header-main-row">
                <div class="brand">
                    <div class="brand-icon">🛍️</div>
                    <span style="font-weight: 800;">Smart Bazaar</span>
                </div>
                <div class="mobile-only-right">
                    <div id="guestHeaderBadge">
                        <a href="/download/release/" class="btn btn-sm btn-outline" style="color: white; border-color: rgba(255,255,255,0.4); font-size: 0.75rem; padding: 5px 9px;">📱 APK</a>
                    </div>
                    <button id="headerLogoutBtnMobile" onclick="logout()" class="btn btn-sm btn-danger" style="display: none; padding: 5px 12px; font-size: 0.78rem; font-weight: 700; border-radius: 8px;">
                        Sign Out
                    </button>
                </div>
            </div>
            <div id="userHeaderBadge" class="header-badge-row" style="display: none;">
                <span id="userRoleBadge" class="badge badge-green header-role-pill"></span>
                <span id="userNameBadge" class="header-user-pill"></span>
                <button id="headerLogoutBtnDesktop" onclick="logout()" class="btn btn-sm btn-danger desktop-only-logout" style="display: none; padding: 5px 14px; font-size: 0.78rem; font-weight: 700; border-radius: 8px; margin-left: 8px;">
                    Sign Out
                </button>
            </div>
        </div>
    </header>

    <main>
        <!-- ======================= 1. LOGIN SECTION ======================= -->
        <section id="loginView" class="view-section active">
            <div class="auth-container card">
                <div style="text-align: center; margin-bottom: 22px;">
                    <div style="width: 52px; height: 52px; margin: 0 auto 12px; background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%); border: 1px solid #BBF7D0; border-radius: 14px; display: inline-flex; align-items: center; justify-content: center; font-size: 1.55rem; box-shadow: 0 4px 12px rgba(15, 81, 50, 0.08);">
                        🔐
                    </div>
                    <h2 style="font-size: 1.45rem; font-weight: 800; color: var(--primary); margin: 0 0 6px 0; letter-spacing: -0.3px;">
                        Portal Access Login
                    </h2>
                    <p style="color: var(--text-muted); font-size: 0.88rem; margin: 0;">
                        Sign in with your Worker Login ID or Admin credentials below.
                    </p>
                </div>

                <!-- Staff Form -->
                <div id="staffForm">
                    <div class="form-group" style="margin-bottom: 16px;">
                        <label style="display: block; font-weight: 700; font-size: 0.82rem; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
                            Username / Staff ID
                        </label>
                        <input type="text" id="staffUsername" class="form-control" placeholder="e.g. admin, owner_grocery, cashier_arun" autocomplete="username">
                    </div>
                    <div class="form-group" style="margin-bottom: 18px;">
                        <label style="display: block; font-weight: 700; font-size: 0.82rem; color: #475569; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px;">
                            Password
                        </label>
                        <div style="position: relative;">
                            <input type="password" id="staffPassword" class="form-control" placeholder="••••••••" autocomplete="current-password" style="padding-right: 44px;">
                            <button type="button" onclick="togglePasswordVisibility('staffPassword', this)" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); background: transparent; border: none; cursor: pointer; color: #64748B; font-size: 1.1rem; padding: 4px;" title="Show/Hide Password">👁️</button>
                        </div>
                    </div>
                    <div id="staffError" style="color: var(--danger); font-size: 0.82rem; margin-bottom: 14px; display: none; background: #FEF2F2; border: 1px solid #FECACA; padding: 8px 12px; border-radius: 8px; font-weight: 600;"></div>
                    <button onclick="handleStaffLogin()" class="btn" style="width: 100%; padding: 12px 18px; font-size: 0.98rem; font-weight: 700; display: flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 4px 14px rgba(15, 81, 50, 0.28);">
                        <span>Sign In as Staff</span> &rarr;
                    </button>
                </div>
            </div>

            <!-- Pre-Seeded Quick Access Card -->
            <div class="card">
                <h3 style="font-size: 1.15rem; font-weight: 700; color: var(--primary); margin-bottom: 8px; display: flex; align-items: center; gap: 8px;">
                    🔑 System Roles &amp; Quick Access
                </h3>
                <p style="color: var(--text-muted); font-size: 0.86rem; margin-bottom: 16px;">
                    Select an authorized role below to sign in or use the login form above:
                </p>

                <div class="table-responsive">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Role</th>
                                <th>Username / Login ID</th>
                                <th>Password</th>
                                <th>Access Privileges</th>
                                <th style="text-align: right;">Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            <!-- LEVEL 1: SUPER ADMIN -->
                            <tr style="background: #F0FDF4;">
                                <td><span class="badge badge-purple" style="font-size: 0.85rem; padding: 6px 14px;">🛡️ Level 1: Super Admin</span></td>
                                <td><strong style="font-size: 0.95rem; color: var(--primary);">admin</strong></td>
                                <td><code>AdminPass@123</code></td>
                                <td style="color: #334155; font-size: 0.88rem;">
                                    <strong>Highest Authority:</strong> Exclusively manages Shop Owner accounts, multi-store provisioning, audits, and brand logo.
                                </td>
                                <td style="text-align: right;">
                                    <button onclick="quickLogin('admin', 'AdminPass@123', 'SUPER_ADMIN')" class="btn btn-sm" style="background: var(--primary); color: white; padding: 8px 16px; font-weight: 700;">⚡ Super Admin</button>
                                </td>
                            </tr>
                            <!-- LEVEL 2: SHOP OWNERS -->
                            <tr>
                                <td><span class="badge badge-blue" style="font-size: 0.85rem; padding: 6px 14px;">👑 Level 2: Shop Owner (Store A)</span></td>
                                <td><strong style="font-size: 0.95rem; color: var(--primary);">owner_grocery</strong></td>
                                <td><code>OwnerPass@123</code></td>
                                <td style="color: #334155; font-size: 0.88rem;">
                                    Owner: <strong>Sushobhan Pratihari</strong> &bull; Shop: <strong>Smart Bazaar Superstore</strong> (<code>SB-SHOP-001</code>). Creates workers, manages products &amp; reports.
                                </td>
                                <td style="text-align: right;">
                                    <button onclick="quickLogin('owner_grocery', 'OwnerPass@123', 'SHOP_OWNER')" class="btn btn-sm btn-outline" style="padding: 8px 16px; font-weight: 700;">⚡ Store A Owner</button>
                                </td>
                            </tr>
                            <tr>
                                <td><span class="badge badge-blue" style="font-size: 0.85rem; padding: 6px 14px;">👑 Level 2: Shop Owner (Store B)</span></td>
                                <td><strong style="font-size: 0.95rem; color: var(--primary);">owner_vikram</strong></td>
                                <td><code>OwnerPass@123</code></td>
                                <td style="color: #334155; font-size: 0.88rem;">
                                    Owner: <strong>Vikram Sen</strong> &bull; Shop: <strong>Seth Retail Mart</strong> (<code>SB-SHOP-522</code>). Tenant-isolated store management.
                                </td>
                                <td style="text-align: right;">
                                    <button onclick="quickLogin('owner_vikram', 'OwnerPass@123', 'SHOP_OWNER')" class="btn btn-sm btn-outline" style="padding: 8px 16px; font-weight: 700;">⚡ Store B Owner</button>
                                </td>
                            </tr>
                        </tbody>
                        <tbody id="quickAccessWorkerRows">
                            <!-- LEVEL 3: WORKERS / CASHIERS -->
                            <tr style="background: #F0FDF4;">
                                <td><span class="badge badge-green" style="font-size: 0.85rem; padding: 6px 14px;">👷 Level 3: Staff (Store A)</span></td>
                                <td><strong style="font-size: 0.95rem; color: #16A34A; font-family: monospace;">cashier_arun</strong></td>
                                <td><code>CashierPass@123</code></td>
                                <td style="color: #334155; font-size: 0.88rem;">
                                    Worker: <strong>Arun Kumar</strong> (ID: <code>SB-EMP-001</code>). Assigned to <strong>Smart Bazaar Superstore</strong>. Barcode scanner &amp; billing only.
                                </td>
                                <td style="text-align: right;">
                                    <button onclick="quickLogin('cashier_arun', 'CashierPass@123', 'WORKER')" class="btn btn-sm" style="background: var(--success); color: white; padding: 8px 16px; font-weight: 700;">⚡ Cashier Terminal</button>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </section>

        <!-- ======================= 2. ADMIN CONTROL CENTER ======================= -->
                <!-- ======================= 2. LEVEL 1: SUPER ADMIN CONTROL CENTER ======================= -->
        <section id="superAdminView" class="view-section">
            <!-- Header bar for Super Admin -->
            <div class="dashboard-hero-card">
                <div class="hero-identity">
                    <div class="hero-icon-box">🛡️</div>
                    <div class="hero-text-block">
                        <div class="hero-badge-wrap">
                            <div><span class="badge badge-purple" style="font-weight: 800; font-size: 0.70rem; padding: 2px 8px;">LEVEL 1: HIGHEST AUTHORITY</span></div>
                            <div class="hero-meta-label">Platform-Wide Governance</div>
                        </div>
                        <h2 class="hero-title">Super Admin Control Center</h2>
                        <p class="hero-desc">
                            Operational Responsibility: <strong>Register, Audit, and Manage Shop Owner Accounts Only.</strong>
                        </p>
                    </div>
                </div>
                <div class="hero-actions">
                    <button type="button" onclick="document.getElementById('shopLogoUploadInput').click()" class="btn btn-sm btn-outline hero-action-btn">
                        <span>🖼️ Upload Store Brand Logo</span>
                    </button>
                    <span class="badge badge-purple hero-status-badge">🛡️ Super Admin Active</span>
                </div>
            </div>

            <!-- KPI Summary Cards -->
            <div class="kpi-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; margin-bottom: 22px;">
                <div class="card kpi-card" style="border-left: 5px solid var(--primary); padding: 16px 20px;">
                    <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Total Registered Shops</div>
                    <div id="statTotalShops" style="font-size: 2rem; font-weight: 800; color: var(--primary); margin-top: 4px;">0</div>
                    <div style="font-size: 0.78rem; color: #64748B;">Multi-store retail network</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #16A34A; padding: 16px 20px;">
                    <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Active Shop Owners</div>
                    <div id="statActiveShops" style="font-size: 2rem; font-weight: 800; color: #16A34A; margin-top: 4px;">0</div>
                    <div style="font-size: 0.78rem; color: #16A34A;">Approved & operating</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #DC2626; padding: 16px 20px;">
                    <div style="font-size: 0.8rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">Suspended / Inactive Owners</div>
                    <div id="statInactiveShops" style="font-size: 2rem; font-weight: 800; color: #DC2626; margin-top: 4px;">0</div>
                    <div style="font-size: 0.78rem; color: #DC2626;">Access revoked</div>
                </div>
            </div>

            <!-- Card: Add New Shop Owner -->
            <div class="card" style="border-top: 4px solid var(--primary); margin-bottom: 22px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px;">
                    <div>
                        <h3 style="font-size: 1.25rem; font-weight: 800; color: var(--primary); margin: 0;">
                            ➕ Add New Shop Owner (Direct Provisioning &amp; Gmail OTP)
                        </h3>
                        <p style="color: var(--text-muted); font-size: 0.84rem; margin: 3px 0 0 0;">
                            Provision a new store owner account. Automatically generates unique Shop ID &amp; Owner Credentials.
                        </p>
                    </div>
                    <span class="badge badge-purple" style="font-size: 0.78rem;">LEVEL 1 &rarr; LEVEL 2</span>
                </div>

                <div class="form-grid" style="margin-top: 16px;">
                    <div class="form-group">
                        <label style="font-weight: 700;">SHOP OWNER FULL NAME *</label>
                        <input type="text" id="ownerFullName" class="form-control" placeholder="e.g. Vikram Sen" required oninput="autoSuggestOwnerLogin();">
                    </div>
                    <div class="form-group">
                        <label style="font-weight: 700;">SHOP / STORE NAME *</label>
                        <input type="text" id="ownerShopName" class="form-control" placeholder="e.g. Sen Retail Mart" required oninput="autoSuggestShopCode();">
                    </div>
                    <div class="form-group">
                        <label style="font-weight: 700;">SHOP MOBILE NUMBER (10 DIGITS) *</label>
                        <input type="tel" id="ownerPhone" class="form-control" placeholder="e.g. 9831012345" maxlength="10" required>
                    </div>
                    <div class="form-group">
                        <label style="font-weight: 700;">SHOP OWNER GMAIL ADDRESS *</label>
                        <input type="email" id="ownerGmail" class="form-control" placeholder="e.g. vikram.owner@gmail.com" required oninput="if(!document.getElementById('ownerUsername').value) autoSuggestOwnerLogin();">
                    </div>
                    <div class="form-group">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <label style="margin: 0; font-weight: 700; color: var(--primary);">UNIQUE SHOP ID *</label>
                            <button type="button" onclick="autoSuggestShopCode(true)" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">⚡ Suggest ID</button>
                        </div>
                        <input type="text" id="ownerShopCode" class="form-control" placeholder="e.g. SB-SHOP-003" style="font-weight: 700; font-family: monospace; color: var(--primary);" value="SB-SHOP-003">
                    </div>
                    <div class="form-group">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <label style="margin: 0; font-weight: 700; color: var(--primary);">UNIQUE OWNER LOGIN ID *</label>
                            <button type="button" onclick="autoSuggestOwnerLogin(true)" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">⚡ Suggest ID</button>
                        </div>
                        <input type="text" id="ownerUsername" class="form-control" placeholder="e.g. owner_vikram or OWNER003" style="font-weight: 700; font-family: monospace; color: #0F5132;">
                    </div>
                    <div class="form-group">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                            <label style="margin: 0; font-weight: 700; color: var(--primary);">PASSWORD / SECURE SETUP *</label>
                            <button type="button" onclick="generateOwnerPassword()" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">🎲 Generate Pass</button>
                        </div>
                        <div style="position: relative;">
                            <input type="password" id="ownerPassword" class="form-control" placeholder="Min 8 chars: Upper, Lower, Num & Symbol" value="OwnerPass@123" style="padding-right: 38px; font-family: monospace; font-weight: 600;">
                            <button type="button" onclick="togglePasswordVisibility('ownerPassword', this)" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; font-size: 0.95rem; opacity: 0.7;">👁️</button>
                        </div>
                    </div>
                    <div class="form-group">
                        <label style="font-weight: 700;">SHOP ADDRESS &amp; LOCATION *</label>
                        <input type="text" id="ownerShopAddress" class="form-control" placeholder="e.g. Station Road, Kolkata - 700001" value="Station Road, Kolkata - 700001">
                    </div>
                </div>

                <!-- OTP Verification Container -->
                <div id="ownerOtpVerifyBox" style="display: none; background: #F8FAFC; border: 1.5px solid var(--border); border-radius: 12px; padding: 16px; margin: 16px 0;">
                    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
                        <span style="font-size: 1.2rem;">📧</span>
                        <h4 style="margin: 0; font-size: 0.95rem; font-weight: 800; color: var(--primary);">
                            Enter Gmail OTP sent to: <span id="ownerOtpTargetEmail" style="color: #0F5132; font-family: monospace;"></span>
                        </h4>
                    </div>
                    <p style="color: var(--text-muted); font-size: 0.82rem; margin-bottom: 12px;">
                        A 6-digit verification code has been dispatched to your Gmail via official Gmail API.
                    </p>
                    <div style="display: flex; gap: 10px; max-width: 400px; width: 100%; flex-wrap: wrap;">
                        <input type="text" id="ownerOtpInput" class="form-control" placeholder="Enter 6-digit OTP" maxlength="6" value="" style="font-weight: 800; font-family: monospace; letter-spacing: 2px; flex: 1 1 140px; min-width: 120px;">
                        <button type="button" onclick="verifyAndCreateShopOwner()" class="btn btn-success" style="white-space: nowrap; font-weight: 700; flex: 1 1 auto;">
                            ✓ Verify &amp; Create Shop Owner
                        </button>
                    </div>
                </div>

                <div style="display: flex; gap: 10px; margin-top: 14px; flex-wrap: wrap;">
                    <button type="button" onclick="sendShopOwnerOtp()" class="btn" style="background: var(--primary); font-weight: 700; padding: 11px 24px; display: inline-flex; align-items: center; gap: 8px;">
                        📧 Send Gmail Verification OTP
                    </button>
                    <button type="button" onclick="quickCreateShopOwnerDirect()" class="btn btn-outline" style="font-weight: 700; border-color: var(--primary); color: var(--primary);">
                        ⚡ 1-Click Provision (Dev Mode)
                    </button>
                </div>
            </div>

            <!-- Card: All Shop Owners Directory -->
            <div class="card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px;">
                    <div>
                        <h3 style="font-size: 1.25rem; font-weight: 800; color: var(--primary); margin: 0;">
                            📋 Registered Shop Owners Directory (<span id="superAdminOwnerCount">0</span> Stores)
                        </h3>
                        <p style="color: var(--text-muted); font-size: 0.84rem; margin: 3px 0 0 0;">
                            Every registered store owner and their authorized shop credentials.
                        </p>
                    </div>
                    <div style="display: flex; gap: 8px; align-items: center; width: 100%; max-width: 280px;">
                        <input type="text" id="searchOwnerInput" oninput="filterSuperAdminOwners()" class="form-control" style="width: 100%; max-width: 280px;" placeholder="🔍 Search owner/store/ID...">
                    </div>
                </div>

                <div class="table-responsive">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Shop Owner</th>
                                <th>Store Name &amp; ID</th>
                                <th>Phone Number</th>
                                <th>Gmail Address</th>
                                <th>Login ID</th>
                                <th>Account Status</th>
                                <th style="text-align: right;">Administrative Actions</th>
                            </tr>
                        </thead>
                        <tbody id="superAdminOwnersTbody"></tbody>
                    </table>
                </div>
            </div>
        </section>

<section id="adminView" class="view-section">
            <!-- Header bar for Shop Owner -->
            <div class="dashboard-hero-card">
                <div class="hero-identity">
                    <div style="position: relative; flex-shrink: 0;">
                        <div id="shopLogoHeaderWrapper" class="hero-icon-box" style="overflow: hidden; padding: 2px;">
                            <span id="shopLogoPlaceholder" style="{shop_placeholder_style}">🛍️</span>
                            <img id="shopLogoHeaderImg" src="{shop_logo_url}" alt="Store Logo" style="{shop_logo_style} width: 100%; height: 100%; object-fit: contain; padding: 2px; background: white;">
                        </div>
                    </div>
                    <div class="hero-text-block">
                        <div class="hero-badge-wrap">
                            <span class="badge badge-blue" style="font-weight: 800; font-size: 0.72rem; padding: 3px 9px;">LEVEL 2: SHOP OWNER</span>
                            <span id="shopDbBadge" class="badge badge-purple" style="font-weight: 700; font-size: 0.70rem; padding: 3px 8px;">🗄️ Database: {shop_info.get('database_name', 'SmartBazaar_Shop_001')} [ACTIVE]</span>
                        </div>
                        <h2 class="hero-title">
                            👑 <span id="ownerStoreName">{shop_info['name']}</span>
                        </h2>
                        <p class="hero-desc">
                            Shop ID: <strong id="ownerStoreCode" style="font-family: monospace; font-weight: 800; color: #0F5132; background: #DCFCE7; padding: 1px 6px; border-radius: 4px;">{shop_info['code']}</strong> &bull; Owner: <strong id="ownerDisplayName">{shop_info['owner_name']}</strong> (Phone: <span id="ownerDisplayPhone">{shop_info['owner_phone']}</span>) &bull; Address: <span id="ownerDisplayAddress">{shop_info['address']}</span>, <span id="ownerDisplayCity">{shop_info['city']}</span>
                        </p>
                    </div>
                </div>
                <div class="hero-actions">
                    <button type="button" onclick="document.getElementById('shopLogoUploadInput').click()" class="btn btn-sm btn-outline hero-action-btn" title="Upload Store Logo">
                        <span>🖼️ Upload Store Logo</span>
                    </button>
                    <button type="button" id="adminNotifBellBtn" onclick="scrollToAdminLowStock()" class="btn btn-sm hero-action-btn" style="background: #F1F5F9; color: #334155; border: 1px solid #CBD5E1;">
                        🔔 Low Stock (&lt;15): <strong id="adminLowStockCount">0</strong>
                    </button>
                    <button type="button" onclick="openOwnerBillingTerminal()" class="btn btn-sm btn-success hero-action-btn" style="font-weight: 700;">
                        ⚡ Open POS Billing
                    </button>
                    <span id="adminStoreBadge" class="badge badge-blue hero-status-badge">👑 Shop Owner Active</span>
                </div>
            </div>

            <!-- First-Time Shop Setup Wizard Card (Requirement 4) -->
            <div id="adminFirstTimeSetupCard" style="display: none; background: #F0FDF4; border: 2px dashed #22C55E; border-radius: 14px; padding: 20px 24px; margin-bottom: 22px;">
                <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 14px;">
                    <div>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 1.8rem;">🚀</span>
                            <h3 style="font-size: 1.25rem; font-weight: 800; color: var(--primary); margin: 0;">
                                Welcome to Your Dedicated Shop Dashboard!
                            </h3>
                            <span class="badge badge-green" style="font-size: 0.72rem;">Independent Database Active</span>
                        </div>
                        <p style="color: #0F5132; font-size: 0.88rem; margin: 6px 0 0 0; max-width: 650px;">
                            Your store database is isolated and clean (0 products, 0 staff, 0 transactions). Complete your profile setup below or start adding your first products.
                        </p>
                    </div>
                    <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                        <button type="button" onclick="switchAdminSection('settings')" class="btn btn-sm btn-outline" style="border-color: var(--primary); color: var(--primary); font-weight: 700;">
                            ⚙️ Setup Profile &amp; Settings
                        </button>
                        <button type="button" onclick="focusAddProductForm()" class="btn btn-sm btn-primary" style="font-weight: 700;">
                            ➕ Add First Product
                        </button>
                        <button type="button" onclick="focusAddWorkerForm()" class="btn btn-sm btn-success" style="font-weight: 700;">
                            👤 Add First Employee
                        </button>
                    </div>
                </div>
            </div>

            <!-- Dynamic KPI Metrics for Authenticated Shop (Requirement 2) -->
            <div class="kpi-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; margin-bottom: 22px;">
                <div class="card kpi-card" style="border-left: 5px solid var(--primary); padding: 14px 16px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">📦 Total Products</div>
                    <div id="kpiShopProducts" style="font-size: 1.8rem; font-weight: 800; color: var(--primary); margin-top: 2px;">0</div>
                    <div style="font-size: 0.75rem; color: #64748B;">In store catalog</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #2563EB; padding: 14px 16px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">👥 Total Employees</div>
                    <div id="kpiShopEmployees" style="font-size: 1.8rem; font-weight: 800; color: #2563EB; margin-top: 2px;">0</div>
                    <div style="font-size: 0.75rem; color: #64748B;">Staff &amp; Cashiers</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #D97706; padding: 14px 16px; cursor: pointer; transition: transform 0.15s ease;" onclick="switchAdminSection('customers')" title="Click to view all customers registered for this store">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">👤 Total Customers</div>
                    <div id="kpiShopCustomers" style="font-size: 1.8rem; font-weight: 800; color: #D97706; margin-top: 2px;">0</div>
                    <div style="font-size: 0.75rem; color: #64748B;">Registered buyers &rarr;</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #16A34A; padding: 14px 16px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">💰 Total Sales</div>
                    <div id="kpiShopSales" style="font-size: 1.8rem; font-weight: 800; color: #16A34A; margin-top: 2px;">₹0.00</div>
                    <div style="font-size: 0.75rem; color: #64748B;">Revenue to date</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #15803D; padding: 14px 16px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">🧾 Total Receipts</div>
                    <div id="kpiShopTransactions" style="font-size: 1.8rem; font-weight: 800; color: #15803D; margin-top: 2px;">0</div>
                    <div style="font-size: 0.75rem; color: #64748B;">Bills checked out</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #0891B2; padding: 14px 16px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">📦 Available Inventory</div>
                    <div id="kpiShopInventory" style="font-size: 1.8rem; font-weight: 800; color: #0891B2; margin-top: 2px;">0</div>
                    <div style="font-size: 0.75rem; color: #64748B;">Total physical units</div>
                </div>
                <div class="card kpi-card" style="border-left: 5px solid #DC2626; padding: 14px 16px;">
                    <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">🚨 Low Stock (&lt;15)</div>
                    <div id="kpiShopLowStock" style="font-size: 1.8rem; font-weight: 800; color: #DC2626; margin-top: 2px;">0</div>
                    <div style="font-size: 0.75rem; color: #64748B;">Need restocking</div>
                </div>
            </div>

            <!-- Automatic Low-Stock Notification Panel for Shop Owner / Admin (< 15 units) -->
            <div id="adminLowStockPanel" style="display: none; background: #FFFBEB; border: 2px solid #F59E0B; border-radius: 14px; padding: 16px 18px; margin-bottom: 20px; box-shadow: 0 4px 18px rgba(245, 158, 11, 0.14);">
                <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 10px; margin-bottom: 10px;">
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <span style="font-size: 1.5rem;">🚨</span>
                        <div>
                            <h3 style="font-size: 1.05rem; font-weight: 800; color: #92400E;">
                                Automatic Low-Stock Alert &mdash; <span id="adminLowStockHeadlineCount">0</span> Product(s) Below 15 Units
                            </h3>
                            <p style="font-size: 0.8rem; color: #B45309;">
                                Every product with remaining quantity less than 15 triggers an automatic alert for restocking.
                            </p>
                        </div>
                    </div>
                    <span class="badge badge-amber" style="font-weight: 800;">THRESHOLD &lt; 15</span>
                </div>
                <div id="adminLowStockList" style="display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 10px; max-height: 220px; overflow-y: auto;"></div>
            </div>

            <!-- Main Shop Owner Navigation Tabs -->
            <div class="nav-tabs" style="background: #DCFCE7; max-width: 960px; margin-bottom: 24px;">
                <div id="tabBtnWorkers" class="nav-tab active" onclick="switchAdminSection('workers')">
                    👥 Shop Employees &amp; Workers (Main Responsibility)
                </div>
                <div id="tabBtnProducts" class="nav-tab" onclick="switchAdminSection('products')">
                    📦 Product Catalog &amp; Stock
                </div>
                <div id="tabBtnCustomers" class="nav-tab" onclick="switchAdminSection('customers')">
                    👥 Store Customers &amp; Loyalty (<span id="tabCustCountBadge">0</span>)
                </div>
                <div id="tabBtnReports" class="nav-tab" onclick="switchAdminSection('reports')">
                    📊 Sales Reports &amp; Receipts
                </div>
                <div id="tabBtnSettings" class="nav-tab" onclick="switchAdminSection('settings')">
                    ⚙️ Store Profile &amp; Settings
                </div>
            </div>

            <!-- ====== SECTION A: PRODUCT MANAGEMENT (ADD WITH QTY, EDIT PRICE, DELETE) ====== -->
            <div id="adminSectionProducts">
                <!-- Notice for Super Admin: Read-only access -->
                <div id="superAdminProductNotice" style="display: none; background: #FEF2F2; border: 2px solid #FECACA; border-radius: 12px; padding: 16px 20px; margin-bottom: 22px; color: #991B1B;">
                    <div style="font-size: 1.05rem; font-weight: 800; display: flex; align-items: center; gap: 8px;">
                        <span>🔒</span> Super Admin Catalog Access: Restricted to Read-Only Audit
                    </div>
                    <p style="margin: 6px 0 0; font-size: 0.88rem; color: #7F1D1D; line-height: 1.4;">
                        Super Admin is strictly prohibited from adding, modifying, or deleting products. Products and store inventory are managed exclusively by authorized Shop Owners.
                    </p>
                </div>

                <!-- Add New Product Form Card (Exclusively for Shop Owners) -->
                <div id="addProductCard" class="card" style="border-top: 4px solid var(--primary);">
                    <h3 style="font-size: 1.2rem; font-weight: 800; color: var(--primary); margin-bottom: 6px;">
                        ➕ Add New Product to Store Catalog (Shop Owner Only)
                    </h3>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 16px;">
                        Specify product name, prices, barcode, and initial stock quantity.
                    </p>

                    <form id="addProductForm" onsubmit="event.preventDefault(); submitAddProduct();">
                        <div class="form-grid">
                            <div class="form-group">
                                <label>Product Name *</label>
                                <input type="text" id="newProdName" class="form-control" placeholder="e.g. Tata Salt 1kg" required>
                            </div>
                            <div class="form-group">
                                <label>Category</label>
                                <input type="text" id="newProdCategory" class="form-control" placeholder="e.g. Grocery, Dairy, Beverages" value="Grocery">
                            </div>
                            <div class="form-group">
                                <label>Barcode (Optional)</label>
                                <input type="text" id="newProdBarcode" class="form-control" placeholder="e.g. 8901030000000">
                            </div>
                            <div class="form-group">
                                <label>Selling Price (₹) *</label>
                                <input type="number" step="0.01" id="newProdPrice" class="form-control" placeholder="0.00" required>
                            </div>
                            <div class="form-group">
                                <label>MRP (₹) *</label>
                                <input type="number" step="0.01" id="newProdMrp" class="form-control" placeholder="0.00" required>
                            </div>
                            <div class="form-group">
                                <label>Initial Quantity (Stock) *</label>
                                <input type="number" step="1" id="newProdQty" class="form-control" placeholder="e.g. 50" value="50" required>
                            </div>
                            <div class="form-group">
                                <label>Unit</label>
                                <select id="newProdUnit" class="form-control">
                                    <option value="PCS">PCS (Pieces)</option>
                                    <option value="KG">KG (Kilogram)</option>
                                    <option value="LTR">LTR (Liter)</option>
                                    <option value="PACK">PACK (Pack)</option>
                                    <option value="BOX">BOX (Box)</option>
                                </select>
                            </div>
                        </div>

                        <div id="addProductMsg" style="display: none; padding: 10px; border-radius: 8px; font-size: 0.85rem; margin-bottom: 12px;"></div>

                        <button type="submit" class="btn" style="background: var(--primary);">
                            💾 Save & Add Product with Quantity
                        </button>
                    </form>
                </div>

                <!-- Products Catalog & Live Stock Table -->
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
                        <div>
                            <h3 style="font-size: 1.2rem; font-weight: 800; color: var(--primary);">
                                📋 Store Products & Inventory (<span id="prodCountBadge">0</span> Items)
                            </h3>
                            <p style="color: var(--text-muted); font-size: 0.85rem;">
                                Edit selling prices, update stock quantities, or delete products.
                            </p>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <a href="/barcodes/" target="_blank" class="btn btn-sm btn-outline" style="border-color: var(--primary); color: var(--primary); font-weight: 700;">
                                📑 View All 200 Barcodes Sheet &rarr;
                            </a>
                            <input type="text" id="searchProductInput" oninput="filterAdminProducts()" class="form-control" style="width: 250px;" placeholder="🔍 Filter products/barcode...">
                        </div>
                    </div>

                    <!-- Empty State for New / Empty Stores (Requirement 9) -->
                    <div id="adminProductsEmptyState" style="display: none; text-align: center; padding: 48px 20px; background: #F0FDF4; border: 2px dashed #C4B5FD; border-radius: 14px; margin: 12px 0;">
                        <div style="font-size: 3.2rem; margin-bottom: 10px;">📦</div>
                        <h4 style="font-size: 1.2rem; font-weight: 800; color: var(--primary); margin: 0 0 6px 0;">No products added yet</h4>
                        <p style="color: #64748B; font-size: 0.88rem; max-width: 460px; margin: 0 auto 16px; line-height: 1.5;">
                            This shop starts completely empty. Add your first product above with custom pricing, barcode, and opening inventory.
                        </p>
                        <button type="button" onclick="focusAddProductForm()" class="btn" style="background: var(--primary); font-weight: 700; padding: 10px 22px;">
                            ➕ Add First Product
                        </button>
                    </div>

                    <div id="adminProductsTableWrapper" class="table-responsive">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Product Name</th>
                                    <th>Barcode</th>
                                    <th>Category</th>
                                    <th>Selling Price</th>
                                    <th>MRP</th>
                                    <th>Current Quantity</th>
                                    <th>Stock Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="adminProductsTbody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ====== SECTION B: WORKER MANAGEMENT WITH GMAIL OTP VERIFICATION ====== -->
            <div id="adminSectionWorkers" style="display: none;">
                <!-- Add Worker with OTP Verification Card -->
                <div class="card" style="border-top: 4px solid var(--secondary);">
                    <h3 style="font-size: 1.2rem; font-weight: 800; color: var(--secondary); margin-bottom: 6px;">
                        👤 Add New Shop Worker with Gmail OTP Verification
                    </h3>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 16px;">
                        Enter the worker's name, phone number, and official Gmail address. Verify via OTP before granting access.
                    </p>

                    <div class="form-grid">
                        <div class="form-group">
                            <label style="font-weight: 700;">WORKER FULL NAME *</label>
                            <input type="text" id="newWorkerName" class="form-control" placeholder="e.g. Vikram Sen" required oninput="autoSuggestWorkerId(); validateWorkerFormLive();">
                        </div>
                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <label style="margin: 0; font-weight: 700; color: var(--primary);">UNIQUE EMPLOYEE ID *</label>
                                <button type="button" onclick="autoSuggestWorkerId(true)" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">⚡ Suggest ID</button>
                            </div>
                            <input type="text" id="newEmployeeCode" class="form-control" placeholder="e.g. SB-EMP-001" style="font-weight: 700; color: #0F5132; font-family: monospace;" value="SB-EMP-001">
                            <small style="color: var(--text-muted); font-size: 0.72rem;">Assigned internal Store Employee ID.</small>
                        </div>
                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <label style="margin: 0; font-weight: 700;">PHONE NUMBER (10 DIGITS ONLY) *</label>
                                <span id="workerPhoneCounter" style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); font-family: monospace;">0/10</span>
                            </div>
                            <input type="tel" id="newWorkerPhone" class="form-control" placeholder="e.g. 9831012345" maxlength="10" inputmode="numeric" required oninput="onWorkerPhoneInput(this)">
                            <div id="workerPhoneFeedback" style="font-size: 0.72rem; margin-top: 4px; font-weight: 600; color: var(--text-muted);">Exact 10 numerical digits only (no spaces or letters).</div>
                        </div>
                        <div class="form-group">
                            <label style="font-weight: 700;">WORKER GMAIL ADDRESS *</label>
                            <input type="email" id="newWorkerEmail" class="form-control" placeholder="e.g. vikram.worker@gmail.com" required oninput="if(!document.getElementById('newWorkerId').value) autoSuggestWorkerId(); validateWorkerFormLive();">
                            <div id="workerEmailFeedback" style="font-size: 0.72rem; margin-top: 4px; font-weight: 600; color: var(--text-muted);">Official Gmail required for OTP verification.</div>
                        </div>
                        <div class="form-group">
                            <label style="font-weight: 700;">STORE ROLE</label>
                            <select id="newWorkerRole" class="form-control" onchange="autoSuggestWorkerId(); validateWorkerFormLive();">
                                <option value="CASHIER">CASHIER (POS Billing Terminal)</option>
                                <option value="MANAGER">MANAGER (Store Management)</option>
                                <option value="STOCK_KEEPER">STOCK KEEPER (Inventory Clerk)</option>
                            </select>
                        </div>
                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <label style="margin: 0; font-weight: 700; color: var(--primary);">UNIQUE WORKER LOGIN ID *</label>
                                <button type="button" onclick="autoSuggestWorkerId(true)" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">⚡ Suggest ID</button>
                            </div>
                            <input type="text" id="newWorkerId" class="form-control" placeholder="e.g. cashier_vikram or WRK-101" required style="font-weight: 700; color: #0F5132; font-family: monospace;" oninput="validateWorkerFormLive();">
                            <small style="color: var(--text-muted); font-size: 0.72rem;">Worker will use this Unique ID to log in.</small>
                        </div>
                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <label style="margin: 0; font-weight: 700; color: var(--primary);">CREATE STRONG PASSWORD *</label>
                                <button type="button" onclick="generateRandomWorkerPassword()" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">🎲 Generate Pass</button>
                            </div>
                            <div style="position: relative;">
                                <input type="password" id="newWorkerPassword" class="form-control" placeholder="Min 8 chars: Upper, Lower, Num & Symbol" required style="padding-right: 38px; font-family: monospace; font-weight: 600;" oninput="onWorkerPasswordInput()">
                                <button type="button" onclick="toggleWorkerPassVisibility('newWorkerPassword', this)" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; font-size: 0.95rem; opacity: 0.7;" title="Show/Hide">👁️</button>
                            </div>
                            <div id="workerPassStrengthBar" style="height: 4px; background: #E2E8F0; border-radius: 2px; margin-top: 6px; overflow: hidden; display: none;">
                                <div id="workerPassStrengthFill" style="height: 100%; width: 0%; background: #EF4444; transition: width 0.3s ease, background 0.3s ease;"></div>
                            </div>
                            <div id="workerPassFeedback" style="font-size: 0.72rem; margin-top: 4px; font-weight: 600; color: var(--text-muted);">8+ chars with uppercase, lowercase, number & symbol.</div>
                        </div>
                        <div class="form-group">
                            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                                <label style="margin: 0; font-weight: 700; color: var(--primary);">VERIFY IT DOUBLE (RETYPE PASSWORD) *</label>
                                <span id="workerPassMatchBadge" style="font-size: 0.72rem; font-weight: 700; display: none;"></span>
                            </div>
                            <div style="position: relative;">
                                <input type="password" id="newWorkerConfirmPassword" class="form-control" placeholder="Retype identical password" required style="padding-right: 38px; font-family: monospace; font-weight: 600;" oninput="onWorkerPasswordInput()">
                                <button type="button" onclick="toggleWorkerPassVisibility('newWorkerConfirmPassword', this)" style="position: absolute; right: 8px; top: 50%; transform: translateY(-50%); background: none; border: none; cursor: pointer; font-size: 0.95rem; opacity: 0.7;" title="Show/Hide">👁️</button>
                            </div>
                            <div id="workerConfirmFeedback" style="font-size: 0.72rem; margin-top: 4px; font-weight: 600; color: var(--text-muted);">Must match the password entered above.</div>
                        </div>
                    </div>

                    <!-- Inline Pre-Validation Error Alert Banner -->
                    <div id="workerPreValidationAlert" style="display: none; background: #FEF2F2; border: 1.5px solid #FCA5A5; color: #B91C1C; padding: 10px 14px; border-radius: 8px; margin-bottom: 14px; font-size: 0.85rem; font-weight: 600; align-items: center; gap: 8px;">
                        <span>⚠️</span>
                        <span id="workerPreValidationAlertText"></span>
                    </div>

                    <!-- Step 1: Send OTP -->
                    <div id="workerOtpStep1">
                        <button type="button" id="btnSendWorkerOtp" onclick="sendWorkerOtp()" class="btn" style="background: var(--secondary); font-weight: 700; padding: 11px 24px; display: inline-flex; align-items: center; gap: 8px; box-shadow: 0 4px 12px rgba(15, 81, 50, 0.18);">
                            📧 Send Verification OTP to Worker Gmail
                        </button>
                    </div>

                    <!-- Step 2: Enter OTP & Grant Access -->
                    <div id="workerOtpStep2" style="display: none; background: #F8FAFC; border: 1.5px solid var(--border); border-radius: 12px; padding: 16px; margin-top: 14px;">
                        <h4 style="font-size: 0.95rem; font-weight: 700; color: var(--primary); margin-bottom: 6px;">
                            🔐 Enter Verification OTP received on Worker's Gmail
                        </h4>
                        <p style="color: var(--text-muted); font-size: 0.82rem; margin-bottom: 12px;">
                            A 6-digit verification code has been dispatched to the worker's Gmail via official Gmail API.
                        </p>
                        <div style="display: flex; gap: 10px; max-width: 380px;">
                            <input type="text" id="workerOtpInput" class="form-control" placeholder="Enter 6-digit OTP" maxlength="6" value="">
                            <button type="button" onclick="verifyAndAddWorker()" class="btn btn-success" style="white-space: nowrap;">
                                ✓ Verify & Grant Access
                            </button>
                        </div>
                    </div>

                    <div id="workerMsg" style="display: none; padding: 12px; border-radius: 8px; font-size: 0.85rem; margin-top: 12px; line-height: 1.5;"></div>
                </div>

                <!-- Active Shop Workers Table -->
                <div class="card">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px;">
                        <div>
                            <h3 style="font-size: 1.2rem; font-weight: 800; color: var(--primary);">
                                👥 Active Shop Workers & Cashiers (<span id="workerCountBadge">0</span> Workers)
                            </h3>
                            <p style="color: var(--text-muted); font-size: 0.85rem;">
                                Authorized staff accounts with Unique Login IDs and POS billing credentials.
                            </p>
                        </div>
                    </div>

                    <!-- Empty State for New Stores with 0 Employees (Requirement 9) -->
                    <div id="adminWorkersEmptyState" style="display: none; text-align: center; padding: 48px 20px; background: #F8FAFC; border: 2px dashed #CBD5E1; border-radius: 14px; margin: 12px 0;">
                        <div style="font-size: 3.2rem; margin-bottom: 10px;">👥</div>
                        <h4 style="font-size: 1.2rem; font-weight: 800; color: #1E293B; margin: 0 0 6px 0;">No employees registered</h4>
                        <p style="color: #64748B; font-size: 0.88rem; max-width: 460px; margin: 0 auto 16px; line-height: 1.5;">
                            No staff members added yet. Create your first cashier or worker account with Gmail OTP verification above.
                        </p>
                        <button type="button" onclick="focusAddWorkerForm()" class="btn" style="background: var(--primary); font-weight: 700; padding: 10px 22px;">
                            👤 Add First Employee
                        </button>
                    </div>

                    <div id="adminWorkersTableWrapper" class="table-responsive">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Worker Name</th>
                                    <th>Unique Login ID</th>
                                    <th>Phone Number</th>
                                    <th>Gmail (Verified)</th>
                                    <th>Store Role</th>
                                    <th>Access Status</th>
                                    <th>Actions</th>
                                </tr>
                            </thead>
                            <tbody id="adminWorkersTbody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ====== SECTION C: STORE CUSTOMERS & BUYERS (COMBINED DIRECTORY) ====== -->
            <div id="adminSectionCustomers" style="display: none;">
                <!-- Section Header with Metrics Cards -->
                <div class="kpi-grid" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 14px; margin-bottom: 20px;">
                    <div class="card kpi-card" style="border-left: 5px solid #D97706; padding: 14px 16px;">
                        <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">👥 Store Customers</div>
                        <div id="kpiSectionStoreCusts" style="font-size: 1.8rem; font-weight: 800; color: #D97706; margin-top: 2px;">0</div>
                        <div style="font-size: 0.75rem; color: #64748B;">Registered across this store</div>
                    </div>
                    <div class="card kpi-card" style="border-left: 5px solid #16A34A; padding: 14px 16px;">
                        <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">💰 Lifetime Customer Spend</div>
                        <div id="kpiSectionStoreSpend" style="font-size: 1.8rem; font-weight: 800; color: #16A34A; margin-top: 2px;">₹0.00</div>
                        <div style="font-size: 0.75rem; color: #64748B;">Cumulative buyer revenue</div>
                    </div>
                    <div class="card kpi-card" style="border-left: 5px solid #2563EB; padding: 14px 16px;">
                        <div style="font-size: 0.75rem; font-weight: 700; color: var(--text-muted); text-transform: uppercase;">✅ Verified Buyers</div>
                        <div id="kpiSectionVerifiedCusts" style="font-size: 1.8rem; font-weight: 800; color: #2563EB; margin-top: 2px;">0</div>
                        <div style="font-size: 0.75rem; color: #64748B;">100% Gmail OTP authenticated</div>
                    </div>
                </div>

                <!-- Customers Directory Card -->
                <div class="card" style="border-top: 4px solid #D97706;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
                        <div>
                            <h3 style="font-size: 1.2rem; font-weight: 800; color: var(--primary);">
                                👥 Registered Store Customers Directory (<span id="storeCustCountBadge">0</span> Customers)
                            </h3>
                            <p style="color: var(--text-muted); font-size: 0.85rem;">
                                Combined list of all buyers added to this store by your cashiers &amp; staff during checkout.
                            </p>
                        </div>
                        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                            <button type="button" onclick="loadShopCustomersFromBackend()" class="btn btn-sm btn-outline" style="border-color: #CBD5E1; color: #334155; font-weight: 700;">
                                🔄 Refresh
                            </button>
                            <input type="text" id="searchStoreCustInput" oninput="filterAdminCustomers()" class="form-control" style="width: 280px;" placeholder="🔍 Filter by name, mobile, code, worker...">
                        </div>
                    </div>

                    <!-- Empty State for Shops with 0 Customers -->
                    <div id="adminCustomersEmptyState" style="display: none; text-align: center; padding: 48px 20px; background: #FFFBEB; border: 2px dashed #FCD34D; border-radius: 14px; margin: 12px 0;">
                        <div style="font-size: 3.2rem; margin-bottom: 10px;">👥</div>
                        <h4 style="font-size: 1.2rem; font-weight: 800; color: #92400E; margin: 0 0 6px 0;">No Customers Registered Yet</h4>
                        <p style="color: #B45309; font-size: 0.88rem; max-width: 500px; margin: 0 auto 16px; line-height: 1.5;">
                            When your cashiers (e.g. Arun Kumar) search for a customer's mobile number at the POS billing terminal, any newly added customer is verified via Gmail OTP and automatically combined here under your store!
                        </p>
                        <button type="button" onclick="openOwnerBillingTerminal()" class="btn btn-sm" style="background: var(--primary); font-weight: 700; color: white; padding: 8px 18px;">
                            ⚡ Open POS Billing Terminal
                        </button>
                    </div>

                    <!-- Customers Table -->
                    <div id="adminCustomersTableWrapper" class="table-responsive">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Customer Code</th>
                                    <th>Full Name</th>
                                    <th>Mobile Number</th>
                                    <th>Gmail (Verified)</th>
                                    <th>Registered By (Worker / Cashier)</th>
                                    <th>Store Visits</th>
                                    <th>Total Spend (₹)</th>
                                    <th>Loyalty Points</th>
                                    <th>Registration Date</th>
                                    <th>Status</th>
                                </tr>
                            </thead>
                            <tbody id="adminCustomersTbody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ====== SECTION C: SALES REPORTS & RECENT RECEIPTS ====== -->
            <div id="adminSectionReports" style="display: none;">
                <div class="card" style="border-top: 4px solid var(--primary);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
                        <div>
                            <h3 style="font-size: 1.2rem; font-weight: 800; color: var(--primary);">
                                📊 Store Transaction &amp; Receipt History
                            </h3>
                            <p style="color: var(--text-muted); font-size: 0.85rem;">
                                Complete log of customer bills generated at this store.
                            </p>
                        </div>
                    </div>

                    <!-- Empty State for New Stores with 0 Sales (Requirement 9) -->
                    <div id="adminReportsEmptyState" style="display: none; text-align: center; padding: 48px 20px; background: #F8FAFC; border: 2px dashed #CBD5E1; border-radius: 14px; margin: 12px 0;">
                        <div style="font-size: 3.2rem; margin-bottom: 10px;">🧾</div>
                        <h4 style="font-size: 1.2rem; font-weight: 800; color: #1E293B; margin: 0 0 6px 0;">No sales transactions available</h4>
                        <p style="color: #64748B; font-size: 0.88rem; max-width: 460px; margin: 0 auto 16px; line-height: 1.5;">
                            No sales receipts have been generated for this store yet. Transactions will appear here as cashiers checkout bills in the POS Terminal.
                        </p>
                        <button type="button" onclick="openOwnerBillingTerminal()" class="btn btn-success" style="font-weight: 700; padding: 10px 22px;">
                            ⚡ Open POS Terminal to Bill
                        </button>
                    </div>

                    <div id="adminReportsTableWrapper" class="table-responsive">
                        <table class="data-table">
                            <thead>
                                <tr>
                                    <th>Bill Number</th>
                                    <th>Customer Name &amp; Phone</th>
                                    <th>Cashier / Worker</th>
                                    <th>Final Total</th>
                                    <th>Payment Mode</th>
                                    <th>Date &amp; Time</th>
                                </tr>
                            </thead>
                            <tbody id="ownerRecentSalesTbody"></tbody>
                        </table>
                    </div>
                </div>
            </div>

            <!-- ====== SECTION D: STORE PROFILE & CONFIGURATION SETTINGS (Requirement 3) ====== -->
            <div id="adminSectionSettings" style="display: none;">
                <div class="card" style="border-top: 4px solid var(--primary);">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 10px;">
                        <div>
                            <h3 style="font-size: 1.25rem; font-weight: 800; color: var(--primary); margin: 0;">
                                ⚙️ Store Profile &amp; Billing Settings
                            </h3>
                            <p style="color: var(--text-muted); font-size: 0.85rem; margin: 4px 0 0 0;">
                                Configure independent shop identity, contact details, UPI QR code, and thermal printer settings.
                            </p>
                        </div>
                        <span id="settStoreCodeBadge" class="badge badge-purple" style="font-family: monospace; font-size: 0.85rem; padding: 6px 12px;">SB-SHOP-001</span>
                    </div>

                    <form id="storeSettingsForm" onsubmit="event.preventDefault(); saveStoreProfileSettings();">
                        <div class="form-grid">
                            <div class="form-group">
                                <label>Store Name *</label>
                                <input type="text" id="settStoreName" class="form-control" placeholder="e.g. Seth Retail Mart" required>
                            </div>
                            <div class="form-group">
                                <label>Unique Shop ID (System Assigned)</label>
                                <input type="text" id="settStoreCode" class="form-control" style="font-family: monospace; font-weight: 700; background: #F1F5F9;" readonly>
                            </div>
                            <div class="form-group">
                                <label>Shop Owner Full Name *</label>
                                <input type="text" id="settOwnerName" class="form-control" placeholder="e.g. Vikram Seth" required>
                            </div>
                            <div class="form-group">
                                <label>Shop Owner Mobile Number *</label>
                                <input type="tel" id="settOwnerPhone" class="form-control" placeholder="10-digit number" required>
                            </div>
                            <div class="form-group">
                                <label>Store Official Contact Phone</label>
                                <input type="tel" id="settStorePhone" class="form-control" placeholder="Shop helpline">
                            </div>
                            <div class="form-group">
                                <label>Store City</label>
                                <input type="text" id="settStoreCity" class="form-control" placeholder="e.g. Kolkata">
                            </div>
                            <div class="form-group" style="grid-column: 1 / -1;">
                                <label>Store Physical Address (Printed on Receipts)</label>
                                <textarea id="settStoreAddress" class="form-control" rows="2" placeholder="Full shop address including landmark and pincode"></textarea>
                            </div>
                            <div class="form-group">
                                <label>Store UPI VPA (For Customer QR Code Payments)</label>
                                <input type="text" id="settStoreUpi" class="form-control" placeholder="e.g. smartbazaar@okaxis">
                            </div>
                            <div class="form-group">
                                <label>Thermal Receipt Printer Width</label>
                                <select id="settReceiptWidth" class="form-control">
                                    <option value="58mm">58mm Thermal Slip (Standard POS Printer)</option>
                                    <option value="80mm">80mm Thermal Receipt (Wide POS Printer)</option>
                                </select>
                            </div>
                        </div>

                        <div id="storeSettingsMsg" style="display: none; padding: 12px; border-radius: 8px; font-size: 0.85rem; margin-top: 14px;"></div>

                        <div style="margin-top: 18px; display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
                            <button type="submit" class="btn" style="background: var(--primary); font-weight: 700; padding: 10px 24px;">
                                💾 Save Store Profile &amp; Settings
                            </button>
                            <button type="button" onclick="document.getElementById('shopLogoUploadInput').click()" class="btn btn-outline" style="border-color: var(--primary); color: var(--primary); font-weight: 700;">
                                🖼️ Change Store Brand Logo
                            </button>
                        </div>
                    </form>
                </div>
            </div>

        </section>

        <!-- ======================= 4. LEVEL 3: STAFF / CASHIER POS VIEW ======================= -->
        <section id="workerPosView" class="view-section">
            <div class="dashboard-hero-card" style="border-left: 6px solid var(--success);">
                <div class="hero-identity">
                    <div class="hero-icon-box" style="background: #ECFDF5; border-color: var(--success); color: var(--success);">⚡</div>
                    <div class="hero-text-block">
                        <div class="hero-badge-wrap">
                            <span class="badge badge-green" style="font-weight: 800; font-size: 0.72rem; padding: 3px 9px;">LEVEL 3: STAFF / CASHIER</span>
                        </div>
                        <h2 class="hero-title" style="color: var(--success);">
                            Cashier POS Billing Terminal
                        </h2>
                        <p class="hero-desc">
                            Cashier Identity: <strong id="posCurrentCashierName">Arun Kumar</strong> (<code id="posCurrentCashierId" style="font-weight: 700;">SB-EMP-001</code>) &bull; Store: <strong id="posCurrentShopName">{shop_info['name']}</strong> (<span id="posCurrentShopCode" style="font-family: monospace; font-weight: 700;">{shop_info['code']}</span>)
                        </p>
                    </div>
                </div>
                <div id="posTopStatusBadge" class="hero-actions">
                    <span id="posStatusBadgeText" class="badge badge-amber hero-status-badge">
                        ⏳ Step 1: Customer Mobile No. Required
                    </span>
                </div>
            </div>

                <!-- ================= STEP 1: MANDATORY CUSTOMER IDENTIFICATION GATE ================= -->
                <div id="posCustomerGateCard" style="background: white; border: 2px solid var(--primary); border-radius: 14px; padding: 18px 20px; margin-bottom: 22px; box-shadow: 0 4px 15px rgba(15, 81, 50, 0.08);">
                    
                    <!-- 1A: Search Customer by Phone -->
                    <div id="posCustSearchStep">
                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <span style="font-size: 1.4rem; background: #DCFCE7; padding: 6px 10px; border-radius: 8px;">📱</span>
                                <div>
                                    <h3 style="font-size: 1.05rem; font-weight: 800; color: var(--primary);">
                                        Step 1: Check Customer Mobile Number
                                    </h3>
                                    <p style="font-size: 0.82rem; color: #64748B;">
                                        Enter customer mobile number. If already registered, details load automatically. If new, register them in 10 seconds!
                                    </p>
                                </div>
                            </div>
                            <button type="button" onclick="continueAsGuest()" class="btn btn-sm btn-outline" style="border-style: dashed; color: #475569; border-color: #94A3B8;">
                                👤 Continue as Walk-in Guest
                            </button>
                        </div>

                        <div style="display: flex; gap: 10px; max-width: 580px; margin-bottom: 12px;">
                            <input type="tel" id="posCustPhoneInput" class="form-control" style="font-size: 1.05rem; font-weight: 700; letter-spacing: 1px;" placeholder="Enter 10-digit Mobile No. (e.g. 9831098310)" maxlength="10" onkeydown="if(event.key==='Enter') searchCustomerPos();">
                            <button type="button" onclick="searchCustomerPos()" class="btn" style="background: var(--primary); white-space: nowrap; font-weight: 700;">
                                🔍 Find / Verify Customer
                            </button>
                        </div>

                        <div id="custSearchError" style="display: none; color: var(--danger); font-size: 0.82rem; margin-bottom: 10px;"></div>

                        <div style="display: flex; align-items: center; gap: 8px; font-size: 0.8rem; color: #64748B; flex-wrap: wrap;">
                            <strong>Quick Test Numbers:</strong>
                            <button type="button" onclick="testCustSearch('9831098310')" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.75rem;">
                                Registered: Rahul Sharma (9831098310)
                            </button>
                            <button type="button" onclick="testCustSearch('9876543210')" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.75rem;">
                                New Customer (9876543210)
                            </button>
                        </div>
                    </div>

                    <!-- 1B: Customer Not Found -> Worker-Assisted Registration -->
                    <div id="posCustRegisterStep" style="display: none;">
                        <div id="regNotFoundBanner" style="background: #FEF3C7; border: 1.5px solid #F59E0B; padding: 14px 18px; border-radius: 12px; margin-bottom: 16px;">
                            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                                <div>
                                    <strong style="color: #92400E; font-size: 0.98rem;">⚠️ Mobile Number Not Registered in Database</strong>
                                    <div style="color: #B45309; font-size: 0.84rem; margin-top: 2px;">Cashier must first add &amp; verify this customer via Gmail OTP before proceeding to billing.</div>
                                </div>
                                <button type="button" onclick="resetCustomerLookup()" class="btn btn-sm btn-outline" style="padding: 4px 12px; font-size: 0.78rem; border-color: #F59E0B; color: #92400E; font-weight: 700;">
                                    &larr; Try Another Mobile No.
                                </button>
                            </div>
                        </div>

                        <div id="regStep1">
                            <div class="form-grid">
                                <div class="form-group">
                                    <label>Customer Full Name *</label>
                                    <input type="text" id="regCustName" class="form-control" placeholder="e.g. Priya Mukherjee" required>
                                </div>
                                <div class="form-group">
                                    <label>Mobile Number (From Lookup) *</label>
                                    <input type="tel" id="regCustPhone" class="form-control" readonly style="background: #F1F5F9; font-weight: 700; color: #1E293B;">
                                </div>
                                <div class="form-group">
                                    <label>Customer Official Gmail Address *</label>
                                    <input type="email" id="regCustEmail" class="form-control" placeholder="e.g. priya.customer@gmail.com" required>
                                </div>
                            </div>

                            <div style="margin-bottom: 14px; font-size: 0.82rem; color: #475569; display: flex; align-items: center; gap: 8px;">
                                <input type="checkbox" id="regCustConsent" checked style="width: 16px; height: 16px; accent-color: var(--primary);">
                                <label for="regCustConsent">Customer has consented to registration and agreed to receive digital bill receipts via Gmail.</label>
                            </div>

                            <div style="display: flex; gap: 10px;">
                                <button type="button" onclick="sendCustomerRegOtp()" class="btn" style="background: var(--secondary);">
                                    📧 Send 6-Digit Gmail Verification OTP
                                </button>
                                <button type="button" onclick="continueAsGuest()" class="btn btn-outline">
                                    Skip & Continue as Walk-in
                                </button>
                            </div>
                        </div>

                        <!-- OTP Verification for Registration -->
                        <div id="regStep2" style="display: none; background: #F8FAFC; border: 1.5px solid var(--border); border-radius: 12px; padding: 16px; margin-top: 14px;">
                            <div id="regOtpMsg" style="font-size: 0.85rem; margin-bottom: 12px; color: #1E293B;"></div>
                            <div style="display: flex; gap: 10px; max-width: 440px;">
                                <input type="text" id="regCustOtp" class="form-control" placeholder="Enter 6-digit OTP" maxlength="6" value="" style="font-weight: 700; letter-spacing: 2px;">
                                <button type="button" id="btnVerifyCustRegOtp" onclick="verifyCustomerRegOtp()" class="btn btn-success" style="white-space: nowrap;">
                                    ✓ Verify OTP & Attach to Bill
                                </button>
                            </div>
                        </div>
                    </div>

                    <!-- 1C: Customer Attached State -->
                    <div id="posCustAttachedStep" style="display: none;">
                        <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px;">
                            <div style="display: flex; align-items: center; gap: 12px;">
                                <div style="width: 44px; height: 44px; border-radius: 50%; background: #DCFCE7; color: #15803D; display: flex; align-items: center; justify-content: center; font-size: 1.4rem; font-weight: 800;">
                                    ✓
                                </div>
                                <div>
                                    <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
                                        <h4 id="attachedCustName" style="font-size: 1.15rem; font-weight: 800; color: #0F172A; margin: 0;">Rahul Sharma</h4>
                                        <span id="attachedCustCode" class="badge badge-purple" style="font-size: 0.75rem;">SB-CUST-774921</span>
                                        <span id="attachedCustRegTag" class="badge badge-green" style="font-size: 0.72rem;">✓ Verified Store Customer</span>
                                    </div>
                                    <div style="font-size: 0.85rem; color: #64748B; margin-top: 3px;">
                                        Phone: <strong id="attachedCustPhone" style="color: #1E293B;">98******10</strong> &bull; 
                                        Email: <strong id="attachedCustEmail" style="color: #1E293B;">ra***@gmail.com</strong> &bull; 
                                        Loyalty Rewards: <strong id="attachedCustPts" style="color: var(--primary); font-size: 0.95rem;">42 Pts</strong>
                                        <span id="attachedCustWorkerInfo" style="margin-left: 6px; color: #0284C7; font-weight: 600;"></span>
                                    </div>
                                </div>
                            </div>
                            <div style="display: flex; gap: 8px; align-items: center;">
                                <span class="badge badge-green" style="font-size: 0.82rem; padding: 6px 12px;">✓ Verified Customer Attached</span>
                                <button type="button" onclick="resetCustomerLookup()" class="btn btn-sm btn-outline" style="border-color: #86EFAC; color: #166534; font-weight: 700;">
                                    🔄 Change Customer
                                </button>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- ================= STEP 2: POS BILLING STATION (LOCKED UNTIL STEP 1 IS COMPLETED) ================= -->
                <div style="position: relative;">
                    <!-- Interactive Lock Banner when Step 1 is pending -->
                    <div id="posLockOverlay" style="position: absolute; inset: 0; background: rgba(248, 250, 252, 0.78); backdrop-filter: blur(2px); z-index: 20; border-radius: 14px; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding-top: 40px; cursor: pointer;" onclick="promptStep1First()">
                        <div style="background: white; border: 2px solid var(--primary); border-radius: 14px; padding: 18px 24px; box-shadow: 0 10px 30px rgba(15, 81, 50, 0.18); text-align: center; max-width: 460px; margin: 0 16px;">
                            <div style="font-size: 1.8rem; margin-bottom: 6px;">🔒</div>
                            <h4 style="color: var(--primary); font-weight: 800; margin-bottom: 6px;">Complete Customer Check (Step 1) First</h4>
                            <p style="font-size: 0.85rem; color: #64748B; margin-bottom: 14px;">
                                Enter customer mobile number above, or click below to bill as a Walk-in Guest and unlock the barcode scanner.
                            </p>
                            <div style="display: flex; gap: 8px; justify-content: center; flex-wrap: wrap;">
                                <button type="button" onclick="event.stopPropagation(); focusCustomerPhoneStep1();" class="btn btn-sm" style="background: var(--primary);">📱 Enter Mobile No.</button>
                                <button type="button" onclick="event.stopPropagation(); continueAsGuest();" class="btn btn-sm btn-outline">👤 Walk-in Guest</button>
                            </div>
                        </div>
                    </div>

                    <div id="posBillingSection" style="opacity: 0.45; transition: all 0.3s ease;">
                        <!-- Instant Barcode Scanner Station (with Text, Image Upload, Drag & Drop, and Webcam) -->
                        <div id="barcodeScannerDropZone"
                             ondragover="event.preventDefault(); this.style.background='#DCFCE7';"
                             ondragleave="this.style.background='#DCFCE7';"
                             ondrop="handleBarcodeDrop(event)"
                             style="background: #DCFCE7; border: 2px dashed var(--primary); border-radius: 12px; padding: 16px; margin-bottom: 20px; transition: background 0.2s;">
                            <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 12px;">
                                <div style="display: flex; align-items: center; gap: 10px;">
                                    <span style="font-size: 1.6rem; background: white; padding: 6px 10px; border-radius: 8px; border: 1px solid var(--border);">📷</span>
                                    <div>
                                        <h4 style="font-size: 1.05rem; font-weight: 800; color: var(--primary);">Instant Barcode Scanner (POS)</h4>
                                        <p style="font-size: 0.8rem; color: #64748B;">Scan barcode, upload a barcode image (PNG/JPG), or drag &amp; drop an image here to auto-add.</p>
                                    </div>
                                </div>
                                <div class="scanner-input-group" style="display: flex; gap: 8px; flex: 1; min-width: 280px; max-width: 680px; flex-wrap: wrap;">
                                    <input type="text" id="posBarcodeInput" class="form-control" style="flex: 1; min-width: 210px; font-family: 'JetBrains Mono', monospace; font-weight: 700; font-size: 0.95rem; letter-spacing: 1px;" placeholder="Scan or type barcode (e.g. 8901000000001)" onkeydown="if(event.key==='Enter'){{ event.preventDefault(); scanBarcodeFromInput(); }}">
                                    <button type="button" onclick="scanBarcodeFromInput()" class="btn" style="background: var(--primary); white-space: nowrap;">⚡ Scan & Add</button>
                                    <button type="button" onclick="document.getElementById('posBarcodeFileInput').click()" class="btn btn-outline" style="background: white; white-space: nowrap; border-color: var(--primary); color: var(--primary);">📤 Upload Barcode Image</button>
                                    <button type="button" onclick="openWebcamScannerModal()" class="btn btn-outline" style="background: white; white-space: nowrap; border-color: #0F5132; color: #0F5132;">📷 Camera</button>
                                    <input type="file" id="posBarcodeFileInput" accept="image/*" style="display: none;" onchange="handleBarcodeImageUpload(event)">
                                </div>
                            </div>

                            <div id="barcodeFeedbackBanner" style="display: none; padding: 10px 12px; border-radius: 8px; font-size: 0.85rem; font-weight: 600; margin-bottom: 10px;"></div>

                            <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-size: 0.8rem;">
                                <div class="quick-barcodes-scroll">
                                    <span style="color: #64748B; font-weight: 700; flex-shrink: 0;">Quick Test:</span>
                                    <button type="button" onclick="simulateBarcodeScan('8901000000001')" class="btn btn-sm btn-outline" style="padding: 3px 8px; font-size: 0.75rem; background: white; flex-shrink: 0;">Atta 5kg (8901000000001)</button>
                                    <button type="button" onclick="simulateBarcodeScan('8901000000026')" class="btn btn-sm btn-outline" style="padding: 3px 8px; font-size: 0.75rem; background: white; flex-shrink: 0;">Sunflower Oil (8901000000026)</button>
                                    <button type="button" onclick="simulateBarcodeScan('8901000000051')" class="btn btn-sm btn-outline" style="padding: 3px 8px; font-size: 0.75rem; background: white; flex-shrink: 0;">Amul Butter (8901000000051)</button>
                                    <button type="button" onclick="simulateBarcodeScan('8901000000126')" class="btn btn-sm btn-outline" style="padding: 3px 8px; font-size: 0.75rem; background: white; flex-shrink: 0;">Maggi Noodles (8901000000126)</button>
                                    <button type="button" onclick="simulateBarcodeScan('8901000000200')" class="btn btn-sm btn-outline" style="padding: 3px 8px; font-size: 0.75rem; background: white; flex-shrink: 0;">Floor Mop (8901000000200)</button>
                                </div>
                                <a href="/api/products/barcode-image/8901000000001/?text=0&download=1" class="btn btn-sm btn-outline" style="padding: 3px 10px; font-size: 0.75rem; background: white; border-color: var(--success); color: var(--success); flex-shrink: 0;" title="Download a valid barcode PNG to test Upload Barcode Image">
                                    ⬇️ Download Sample Barcode PNG
                                </a>
                            </div>
                        </div>

                        <div class="pos-grid">
                            <!-- Left Section: Scanned Items Bill Table (Products auto-added by scanning barcode) -->
                            <div class="card" style="margin-bottom: 0; background: white; border: 1.5px solid var(--border); border-radius: 14px; padding: 20px; box-shadow: 0 4px 15px rgba(0,0,0,0.03);">
                                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; flex-wrap: wrap; gap: 8px;">
                                    <div>
                                        <h4 style="font-size: 1.15rem; font-weight: 800; color: var(--primary); margin: 0; display: flex; align-items: center; gap: 8px;">
                                            🛒 Scanned Billing Items (<span id="cartCountBadge">0</span>)
                                        </h4>
                                        <p style="color: var(--text-muted); font-size: 0.84rem; margin: 4px 0 0 0;">
                                            Scan barcodes using handheld scanner, input box, or camera &mdash; products are automatically added.
                                        </p>
                                    </div>
                                    <button type="button" onclick="clearCart()" class="btn btn-sm btn-outline" style="border-color: #CBD5E1; color: #64748B; font-size: 0.78rem;">
                                        🗑️ Clear Bill
                                    </button>
                                </div>

                                <div class="table-responsive" style="max-height: 440px; overflow-y: auto;">
                                    <table class="cart-table" style="width: 100%;">
                                        <thead>
                                            <tr style="border-bottom: 2px solid #E2E8F0; background: #F8FAFC;">
                                                <th style="padding: 10px 12px; font-size: 0.82rem; text-align: left;">Product / Barcode</th>
                                                <th style="padding: 10px 12px; font-size: 0.82rem; text-align: right;">Unit Price</th>
                                                <th style="padding: 10px 12px; font-size: 0.82rem; text-align: center;">Qty</th>
                                                <th style="padding: 10px 12px; font-size: 0.82rem; text-align: right;">Total</th>
                                                <th style="padding: 10px 12px; font-size: 0.82rem; text-align: center;">Action</th>
                                            </tr>
                                        </thead>
                                        <tbody id="cartTbody">
                                            <tr>
                                                <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 42px 14px;">
                                                    <div style="font-size: 2.4rem; margin-bottom: 8px;">📷</div>
                                                    <strong style="font-size: 1.05rem; color: #1E293B; display: block; margin-bottom: 4px;">Ready to Scan Barcodes</strong>
                                                    <span style="font-size: 0.85rem;">Scan any product barcode above or use handheld scanner to automatically add products to this bill.</span>
                                                </td>
                                            </tr>
                                        </tbody>
                                    </table>
                                </div>
                            </div>

                            <!-- Right Section: Bill Summary & Checkout -->
                            <div id="posCartSection" class="pos-cart-sticky" style="border-radius: 14px; padding: 20px;">
                                <h4 style="font-size: 1.15rem; font-weight: 800; margin-bottom: 14px; color: var(--primary); display: flex; align-items: center; justify-content: space-between;">
                                    <span>🧾 Bill Summary</span>
                                    <span id="cartItemCountSummaryBadge" class="badge badge-purple" style="font-size: 0.75rem; padding: 4px 10px;">0 Items</span>
                                </h4>

                                <div style="font-size: 0.92rem; display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px;">
                                    <div style="display: flex; justify-content: space-between;">
                                        <span style="color: #64748B;">Subtotal:</span>
                                        <strong id="cartSubtotal" style="color: #1E293B;">₹0.00</strong>
                                    </div>
                                    <div style="display: flex; justify-content: space-between;">
                                        <span style="color: #64748B;">GST &amp; Taxes:</span>
                                        <span id="cartTax" style="color: #64748B; font-weight: 600;">₹0.00</span>
                                    </div>
                                    <div style="display: flex; justify-content: space-between; border-top: 1.5px dashed #CBD5E1; padding-top: 10px; margin-top: 4px; font-size: 1.35rem; font-weight: 800; color: var(--primary);">
                                        <span>Total Payable:</span>
                                        <span id="cartFinalTotal">₹0.00</span>
                                    </div>
                                </div>

                                <!-- Payment Mode Selector (Cash vs Razorpay Online QR) -->
                                <div style="margin-bottom: 14px; background: #F8FAFC; border: 1.5px solid #E2E8F0; border-radius: 12px; padding: 12px;">
                                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                                        <label style="font-size: 0.78rem; font-weight: 800; color: #475569; text-transform: uppercase; letter-spacing: 0.6px; margin: 0;">
                                            Payment Mode (Customer Choice):
                                        </label>
                                        <span id="paymentModeBadge" class="badge badge-green" style="font-size: 0.68rem; padding: 2px 7px;">Cash Selected</span>
                                    </div>
                                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                                        <button type="button" id="payModeBtnCash" onclick="setPosPaymentMode('CASH')" style="padding: 10px; border-radius: 10px; border: 2px solid #16A34A; background: #DCFCE7; color: #15803D; font-weight: 800; font-size: 0.88rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; box-shadow: 0 2px 6px rgba(22, 163, 74, 0.15); transition: all 0.2s;">
                                            <span>💵 Cash</span>
                                        </button>
                                        <button type="button" id="payModeBtnOnline" onclick="setPosPaymentMode('ONLINE')" style="padding: 10px; border-radius: 10px; border: 1.5px solid #CBD5E1; background: #FFFFFF; color: #475569; font-weight: 700; font-size: 0.88rem; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px; transition: all 0.2s;">
                                            <span>⚡ Online (UPI QR)</span>
                                        </button>
                                    </div>
                                </div>

                                <button type="button" id="posMainCheckoutBtn" onclick="handlePosCheckoutAction()" class="btn btn-success" style="width: 100%; padding: 13px; font-size: 1rem; font-weight: 800; display: flex; align-items: center; justify-content: center; gap: 8px; box-shadow: 0 4px 14px rgba(22, 163, 74, 0.25);">
                                    <span id="posMainCheckoutBtnLabel">💵 Complete Cash Checkout &amp; Print Bill</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Mobile Sticky Floating Cart Bar -->
            <div id="mobileCartFloatBar" class="mobile-cart-float" onclick="scrollToCart()" style="display: none;">
                <div style="display: flex; align-items: center; gap: 10px;">
                    <div style="background: rgba(255,255,255,0.2); width: 36px; height: 36px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 1.15rem;">🛒</div>
                    <div>
                        <strong id="mobCartCountText" style="font-size: 0.95rem; color: white;">0 Items</strong>
                        <div id="mobCartTotalText" style="font-size: 0.8rem; color: #DCFCE7; font-weight: 700;">₹0.00 Total</div>
                    </div>
                </div>
                <button type="button" class="btn btn-sm btn-success" style="padding: 7px 14px; font-weight: 800; border-radius: 8px;">
                    View Cart &amp; Pay &rarr;
                </button>
            </div>
        </section>

        <!-- ======================= 4. CUSTOMER PHONEPE VIEW ======================= -->
        <section id="customerView" class="view-section">
            <div class="card" style="border-left: 6px solid var(--primary); background: linear-gradient(180deg, #FFFFFF 0%, #F0FDF4 100%);">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                    <div>
                        <span class="badge badge-purple" style="margin-bottom: 6px;">PHONEPE FINTECH DASHBOARD</span>
                        <h2 style="font-size: 1.5rem; font-weight: 800; color: var(--primary);">Hello, Rahul Sharma! 👋</h2>
                        <p style="color: var(--text-muted); font-size: 0.88rem;">Member ID: <code>CUST-849201</code> &bull; Email: rahul.customer@gmail.com</p>
                    </div>
                    <div style="background: white; border: 2px solid var(--primary); border-radius: 12px; padding: 10px; text-align: center; box-shadow: 0 4px 12px rgba(95,37,159,0.1);">
                        <div style="width: 70px; height: 70px; background: #DCFCE7; display: flex; align-items: center; justify-content: center; font-size: 1.8rem; border-radius: 8px;">
                            📱
                        </div>
                        <span style="font-size: 0.7rem; font-weight: 700; color: var(--primary); display: block; margin-top: 4px;">SCAN AT POS</span>
                    </div>
                </div>

                <div style="background: white; border: 1.5px solid var(--border); border-radius: 14px; padding: 18px; margin-bottom: 20px;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <span style="font-weight: 600; color: #475569;">Lifetime Spend Milestone</span>
                        <strong style="color: var(--primary); font-size: 1.1rem;">₹1,500 / ₹15,000</strong>
                    </div>
                    <div style="width: 100%; height: 12px; background: #E2E8F0; border-radius: 999px; overflow: hidden; margin-bottom: 10px;">
                        <div style="width: 10%; height: 100%; background: linear-gradient(90deg, #0F5132, #22C55E); border-radius: 999px;"></div>
                    </div>
                    <span style="font-size: 0.82rem; color: var(--success); font-weight: 600;">
                        🎉 Spend ₹13,500 more to unlock your flat ₹50 Loyalty Reward Voucher!
                    </span>
                </div>

                <div class="kpi-grid">
                    <div class="kpi-card">
                        <span class="kpi-title">Smart Bazaar Rewards</span>
                        <span class="kpi-value">150 Pts</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">Wallet Balance</span>
                        <span class="kpi-value" style="color: var(--success);">₹0.00</span>
                    </div>
                    <div class="kpi-card">
                        <span class="kpi-title">Active Coupons</span>
                        <span class="kpi-value">1 Coupon (FESTIVE50)</span>
                    </div>
                </div>

                <h3 style="font-size: 1.1rem; margin-bottom: 12px; font-weight: 700;">Previous Purchases & Bills</h3>
                <div class="table-responsive">
                    <table class="data-table">
                        <thead>
                            <tr>
                                <th>Bill #</th>
                                <th>Shop</th>
                                <th>Total Amount</th>
                                <th>Payment</th>
                                <th>Date</th>
                            </tr>
                        </thead>
                        <tbody id="customerBillsTbody"></tbody>
                    </table>
                </div>
            </div>
        </section>
    </main>

    <!-- Mobile-First Bottom Navigation Bar (Visible on Android & Mobile Screens) -->
    <nav id="mobileBottomNav" class="mobile-bottom-nav">
        <!-- Rendered dynamically by role in renderMobileBottomNav() -->
    </nav>

    <!-- Mobile Cart Bottom Sheet Drawer (One-Handed POS Checkout) -->
    <div id="mobileCartDrawer" class="mobile-cart-drawer" onclick="if(event.target===this) closeMobileCartDrawer();">
        <div class="mobile-cart-sheet">
            <div class="drawer-pill-handle"></div>
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; border-bottom: 1px solid #E2E8F0; padding-bottom: 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 1.3rem;">🛒</span>
                    <h3 style="margin: 0; font-size: 1.15rem; font-weight: 800; color: #0F5132;">Current Bill Cart</h3>
                    <span id="drawerCartBadge" class="badge badge-green">0 Items</span>
                </div>
                <button type="button" onclick="closeMobileCartDrawer()" style="background: #F1F5F9; border: none; font-size: 1.1rem; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; color: #64748B;">✕</button>
            </div>
            
            <div id="drawerCartItems" style="max-height: 42vh; overflow-y: auto; margin-bottom: 14px;">
                <!-- Populated by renderCart() -->
            </div>

            <!-- Customer & Payment Quick Selector -->
            <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 14px; padding: 12px; margin-bottom: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                    <span style="font-weight: 700; font-size: 0.82rem; color: #475569;">CUSTOMER</span>
                    <span id="drawerCustomerLabel" style="font-size: 0.82rem; color: #0F5132; font-weight: 700;">Walk-in Customer</span>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem; color: #64748B; margin-bottom: 4px;">
                    <span>Subtotal:</span>
                    <strong id="drawerSubtotal" style="color: #0F172A;">₹0.00</strong>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.82rem; color: #64748B; margin-bottom: 8px;">
                    <span>GST (Tax):</span>
                    <strong id="drawerTax" style="color: #0F172A;">₹0.00</strong>
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 1.15rem; font-weight: 800; color: #0F5132; border-top: 1px dashed #CBD5E1; padding-top: 8px;">
                    <span>Grand Total:</span>
                    <span id="drawerGrandTotal">₹0.00</span>
                </div>
            </div>

            <!-- Payment Methods Pill Selector -->
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 6px; margin-bottom: 14px;">
                <button type="button" onclick="selectDrawerPayment('CASH')" id="payBtnCash" class="btn btn-sm" style="background: #0F5132; color: white; border-radius: 10px; font-weight: 700;">
                    💵 Cash
                </button>
                <button type="button" onclick="selectDrawerPayment('UPI')" id="payBtnUPI" class="btn btn-sm btn-outline" style="border-color: #0F5132; color: #0F5132; border-radius: 10px; font-weight: 700;">
                    📱 UPI / QR
                </button>
                <button type="button" onclick="selectDrawerPayment('CARD')" id="payBtnCard" class="btn btn-sm btn-outline" style="border-color: #0F5132; color: #0F5132; border-radius: 10px; font-weight: 700;">
                    💳 Card
                </button>
            </div>

            <!-- Complete Bill Button -->
            <button type="button" onclick="checkoutFromDrawer()" class="btn btn-success" style="width: 100%; min-height: 52px; font-size: 1.05rem; font-weight: 800; border-radius: 14px; box-shadow: 0 4px 16px rgba(15, 81, 50, 0.35); display: flex; align-items: center; justify-content: center; gap: 8px;">
                <span>Complete Bill &amp; Print Receipt</span> &rarr;
            </button>
        </div>
    </div>

    <!-- Global Modal: Razorpay Dynamic QR & Online Payment Flow -->
    <div id="razorpayPaymentModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.72); z-index: 10000; justify-content: center; align-items: center;" onclick="if(event.target===this) closeRazorpayModal();">
        <div style="background: white; border-radius: 20px; padding: 24px; max-width: 440px; width: 92%; max-height: 94vh; overflow-y: auto; box-shadow: 0 16px 48px rgba(0,0,0,0.35); text-align: center; position: relative;">
            
            <!-- Modal Header -->
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #E2E8F0; padding-bottom: 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 1.4rem;">⚡</span>
                    <div style="text-align: left;">
                        <h4 style="font-weight: 800; color: #0F5132; margin: 0; font-size: 1.05rem;">Razorpay Online / UPI QR</h4>
                        <span class="badge badge-purple" style="font-size: 0.68rem; margin-top: 2px;">Automated Real-Time Detection</span>
                    </div>
                </div>
                <button type="button" onclick="closeRazorpayModal()" style="background: #F1F5F9; border: none; font-size: 1.1rem; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; color: #64748B;">✕</button>
            </div>

            <!-- Amount Highlight Box -->
            <div style="background: #F0FDF4; border: 1.5px solid #86EFAC; border-radius: 12px; padding: 12px 16px; margin-bottom: 14px;">
                <div style="font-size: 0.78rem; font-weight: 800; color: #166534; text-transform: uppercase; letter-spacing: 0.8px;">Exact Amount to Scan &amp; Pay</div>
                <div id="rzpModalAmountText" style="font-size: 2.2rem; font-weight: 900; color: #0F5132; margin-top: 2px;">₹0.00</div>
                <div id="rzpModalCustomerText" style="font-size: 0.78rem; color: #475569; margin-top: 2px;">Customer: Walk-in Guest</div>
            </div>

            <!-- Dynamic QR Code Card -->
            <div id="rzpQrCardContainer" style="background: #FFFFFF; border: 2px solid #0F5132; border-radius: 14px; padding: 16px; margin: 0 auto 14px auto; max-width: 270px; box-shadow: 0 4px 16px rgba(15,81,50,0.12); position: relative;">
                <img id="rzpQrImage" src="" alt="Dynamic Razorpay UPI QR" style="width: 210px; height: 210px; object-fit: contain; display: block; margin: 0 auto;">
                <div style="display: flex; justify-content: center; align-items: center; gap: 6px; margin-top: 10px;">
                    <span style="font-size: 0.72rem; font-weight: 800; color: #0F5132; letter-spacing: 0.5px;">POWERED BY RAZORPAY UPI</span>
                </div>
            </div>

            <!-- Supported UPI Apps Badges -->
            <div style="font-size: 0.75rem; color: #64748B; margin-bottom: 14px; display: flex; justify-content: center; gap: 6px; flex-wrap: wrap;">
                <span class="badge" style="background:#F1F5F9; color:#0F172A; border:1px solid #CBD5E1;">Google Pay</span>
                <span class="badge" style="background:#F1F5F9; color:#0F172A; border:1px solid #CBD5E1;">PhonePe</span>
                <span class="badge" style="background:#F1F5F9; color:#0F172A; border:1px solid #CBD5E1;">Paytm</span>
                <span class="badge" style="background:#F1F5F9; color:#0F172A; border:1px solid #CBD5E1;">BHIM</span>
                <span class="badge" style="background:#F1F5F9; color:#0F172A; border:1px solid #CBD5E1;">CRED</span>
            </div>

            <!-- Live Status Area -->
            <div id="rzpLiveStatusBox" style="padding: 12px; border-radius: 12px; background: #FFFBEB; border: 1.5px solid #FDE68A; margin-bottom: 14px;">
                <div id="rzpStatusText" style="font-size: 0.88rem; font-weight: 700; color: #92400E; display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <span style="font-size: 1.2rem;">⏳</span>
                    <span>Waiting for customer to scan &amp; complete payment...</span>
                </div>
            </div>

            <!-- Post-Success Action (Revealed automatically upon payment detected) -->
            <div id="rzpSuccessActions" style="display: none; flex-direction: column; gap: 10px; margin-bottom: 8px;">
                <button type="button" onclick="completeOnlineCheckoutAndPrint()" class="btn btn-success" style="width: 100%; padding: 14px; font-size: 1.05rem; font-weight: 800; border-radius: 12px; box-shadow: 0 4px 16px rgba(22, 163, 74, 0.35); display: flex; align-items: center; justify-content: center; gap: 8px;">
                    <span>🖨️ Print Bill &amp; Complete (Send Gmail Receipt)</span>
                </button>
            </div>

            <!-- Quick Helpers (Open link directly or simulate in test mode) -->
            <div id="rzpDevHelpers" style="display: flex; justify-content: space-between; align-items: center; margin-top: 10px; border-top: 1px dashed #E2E8F0; padding-top: 8px;">
                <a id="rzpDirectPayLink" href="#" target="_blank" style="font-size: 0.74rem; color: #2563EB; font-weight: 700; text-decoration: none;">
                    Open Checkout Page ↗
                </a>
                <button type="button" onclick="simulateRazorpayApproval()" class="btn btn-sm" style="background: #F1F5F9; color: #475569; font-size: 0.72rem; padding: 4px 8px; border-radius: 6px;">
                    ⚡ Simulate Success (Dev Test)
                </button>
            </div>

        </div>
    </div>

    <!-- Global Modal: Thermal Receipt -->
    <div id="receiptModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 9999; justify-content: center; align-items: center;" onclick="if(event.target===this) closeReceipt();">
        <div style="background: white; border-radius: 16px; padding: 22px; max-width: 430px; width: 92%; max-height: 90vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.35);">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; border-bottom: 1px solid #E2E8F0; padding-bottom: 10px;">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <span style="font-size: 1.3rem;">🧾</span>
                    <div>
                        <h4 style="font-weight: 800; color: #0F5132; margin: 0; font-size: 1.05rem;">Official Store Receipt</h4>
                        <span id="receiptWidthBadge" class="badge badge-green" style="font-size: 0.68rem; margin-top: 2px;">58mm Thermal</span>
                    </div>
                </div>
                <button onclick="closeReceipt()" style="background: #F1F5F9; border: none; font-size: 1.1rem; width: 32px; height: 32px; border-radius: 50%; cursor: pointer; color: #64748B;">✕</button>
            </div>

            <!-- 58mm vs 80mm Thermal Switcher -->
            <div style="display: flex; gap: 6px; margin-bottom: 12px; background: #F1F5F9; padding: 3px; border-radius: 10px;">
                <button type="button" onclick="setReceiptWidth(58)" id="btnReceipt58" style="flex: 1; padding: 6px; border: none; border-radius: 8px; background: #0F5132; color: white; font-weight: 700; font-size: 0.78rem; cursor: pointer;">
                    58mm (Mobile)
                </button>
                <button type="button" onclick="setReceiptWidth(80)" id="btnReceipt80" style="flex: 1; padding: 6px; border: none; border-radius: 8px; background: transparent; color: #475569; font-weight: 700; font-size: 0.78rem; cursor: pointer;">
                    80mm (Counter)
                </button>
            </div>

            <!-- Digital Gmail & PDF Dispatch Status Banner -->
            <div id="receiptEmailStatusBanner" style="display: none; padding: 10px 12px; border-radius: 10px; margin-bottom: 12px; font-size: 0.78rem; line-height: 1.4;"></div>

            <div id="receiptContainerBox" style="max-height: 52vh; overflow-y: auto; background: #FFFDF9; border: 1.5px dashed #CBD5E1; border-radius: 12px; padding: 14px; margin-bottom: 14px; position: relative;">
                <div id="receiptContent" style="font-family: 'JetBrains Mono', monospace; font-size: 0.8rem; line-height: 1.4; color: #0F172A; white-space: pre-wrap; width: 100%; margin: 0 auto; position: relative; z-index: 1;"></div>
            </div>
            
            <!-- Quick Actions Grid -->
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                <button onclick="printThermalReceipt()" class="btn btn-sm" style="background: #0F5132; color: white; font-weight: 700; padding: 11px; border-radius: 10px;">
                    🖨️ Print Receipt
                </button>
                <button onclick="shareReceipt()" class="btn btn-sm" style="background: #22C55E; color: #0A3622; font-weight: 800; padding: 11px; border-radius: 10px; box-shadow: 0 2px 8px rgba(34,197,94,0.3);">
                    📱 Share (WhatsApp)
                </button>
            </div>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <button onclick="downloadThermalReceipt()" class="btn btn-sm btn-outline" style="border-color: #0F5132; color: #0F5132; font-weight: 700; padding: 9px; border-radius: 10px;">
                    ⬇️ Download Text
                </button>
                <button onclick="copyReceiptText()" class="btn btn-sm btn-outline" style="border-color: #CBD5E1; color: #475569; font-weight: 700; padding: 9px; border-radius: 10px;">
                    📋 Copy Text
                </button>
            </div>
        </div>
    </div>

    <!-- Global Modal: Barcode Tag Viewer (Accessible from Any View) -->
    <div id="barcodeTagModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 9999; justify-content: center; align-items: center;" onclick="if(event.target===this) closeBarcodeModal();">
        <div style="background: white; border-radius: 16px; padding: 24px; max-width: 440px; width: 92%; box-shadow: 0 10px 40px rgba(0,0,0,0.3); text-align: center; position: relative;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 0.8rem; font-weight: 800; color: var(--primary); text-transform: uppercase; letter-spacing: 0.5px;">🏷️ Smart Bazaar Shelf Barcode Tag</span>
                <button onclick="closeBarcodeModal()" style="background: none; border: none; font-size: 1.4rem; cursor: pointer; color: #64748B; line-height: 1;">✕</button>
            </div>

            <h3 id="modalProdTitle" style="font-size: 1.15rem; font-weight: 800; color: #1E293B; margin-bottom: 4px;"></h3>
            <div id="modalProdCategory" style="font-size: 0.8rem; color: #64748B; margin-bottom: 14px;"></div>

            <div style="display: flex; justify-content: center; align-items: baseline; gap: 12px; margin-bottom: 16px;">
                <span id="modalProdPrice" style="font-size: 1.5rem; font-weight: 800; color: var(--success);"></span>
                <span id="modalProdMrp" style="font-size: 0.95rem; color: #94A3B8; text-decoration: line-through;"></span>
                <span id="modalProdStock" class="badge badge-green" style="font-size: 0.8rem;"></span>
            </div>

            <!-- 1D BARCODE IMAGE (MATCHING USER REFERENCE) -->
            <div style="background: #FFFFFF; border: 1.5px solid var(--border); border-radius: 12px; padding: 18px 12px; margin-bottom: 16px; box-shadow: 0 2px 8px rgba(0,0,0,0.04);">
                <img id="modalBarcodeImg" src="" alt="Product Barcode" style="max-width: 100%; height: 85px; object-fit: contain; display: block; margin: 0 auto;">
                <div id="modalBarcodeNum" style="font-family: 'JetBrains Mono', monospace; font-size: 1.05rem; font-weight: 700; letter-spacing: 2px; margin-top: 8px; color: #1E293B;"></div>
            </div>

            <p style="font-size: 0.8rem; color: #64748B; margin-bottom: 16px;">
                Point your mobile camera, APK scanner, or USB reader at this 1D barcode to test instant automated item detection!
            </p>

            <div style="display: flex; gap: 8px;">
                <button id="modalScanPosBtn" onclick="modalScanToPos()" class="btn" style="flex: 1.5; background: var(--primary);">
                    ⚡ Test Scan to POS
                </button>
                <a id="modalDownloadLink" href="#" download class="btn btn-outline" style="flex: 1;">
                    ⬇️ PNG
                </a>
                <button onclick="window.print()" class="btn btn-outline" style="flex: 1;">
                    🖨️ Print
                </button>
            </div>
        </div>
    </div>

    <!-- Global Modal: Live Webcam / Image Barcode Scanner -->
    <div id="webcamScannerModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.75); z-index: 9999; justify-content: center; align-items: center;" onclick="if(event.target===this) closeWebcamScannerModal();">
        <div style="background: white; border-radius: 16px; padding: 22px; max-width: 480px; width: 92%; box-shadow: 0 12px 45px rgba(0,0,0,0.35); text-align: center;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <h4 style="font-weight: 800; color: var(--primary);">📷 Live Camera Barcode Scanner</h4>
                <button onclick="closeWebcamScannerModal()" style="background: none; border: none; font-size: 1.4rem; cursor: pointer; color: #64748B;">✕</button>
            </div>
            <div style="position: relative; background: #0F172A; border-radius: 12px; overflow: hidden; margin-bottom: 12px; min-height: 240px; display: flex; align-items: center; justify-content: center;">
                <video id="webcamPreviewVideo" autoplay playsinline style="width: 100%; max-height: 300px; object-fit: cover; display: block;"></video>
                <div style="position: absolute; width: 70%; height: 110px; border: 2px solid #22C55E; border-radius: 10px; box-shadow: 0 0 0 9999px rgba(0,0,0,0.28); pointer-events: none;"></div>
                <canvas id="webcamCaptureCanvas" style="display: none;"></canvas>
            </div>
            <div id="webcamStatusText" style="font-size: 0.85rem; color: #475569; font-weight: 600; margin-bottom: 12px;">
                Hold a barcode image in front of your camera...
            </div>
            <div style="display: flex; gap: 8px; justify-content: center;">
                <button type="button" onclick="document.getElementById('posBarcodeFileInput').click(); closeWebcamScannerModal();" class="btn btn-outline" style="flex: 1;">
                    📤 Upload Barcode Image Instead
                </button>
                <button type="button" onclick="closeWebcamScannerModal()" class="btn btn-danger">Close</button>
            </div>
        </div>
    </div>

    <!-- Floating Live Low-Stock Notification Popup (< 15 units) -->
    <div id="lowStockToast" style="display: none; position: fixed; top: 80px; right: 20px; z-index: 99999; max-width: 390px; background: #FFFBEB; border: 2px solid #F59E0B; border-left: 6px solid #DC2626; border-radius: 12px; padding: 14px 16px; box-shadow: 0 12px 35px rgba(0,0,0,0.22); color: #78350F;"></div>

    <!-- Global Modal: Worker Password Reset -->
    <div id="workerResetPassModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 99999; justify-content: center; align-items: center;" onclick="if(event.target===this) closeWorkerResetPassModal();">
        <div style="background: white; border-radius: 16px; padding: 24px; max-width: 440px; width: 92%; box-shadow: 0 12px 40px rgba(0,0,0,0.3); position: relative;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 0.9rem; font-weight: 800; color: var(--primary); text-transform: uppercase; letter-spacing: 0.5px;">🔑 Reset Worker Login Password</span>
                <button onclick="closeWorkerResetPassModal()" style="background: none; border: none; font-size: 1.4rem; cursor: pointer; color: #64748B; line-height: 1;">✕</button>
            </div>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 14px;">
                Update cashier/worker password for <strong id="resetModalWorkerName" style="color: var(--primary);"></strong> (<code id="resetModalWorkerId" style="color: var(--secondary); font-weight: 700;"></code>).
            </p>
            <input type="hidden" id="resetModalUserId">
            <div class="form-group" style="margin-bottom: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label style="margin: 0; font-weight: 700; font-size: 0.85rem;">New Login Password *</label>
                    <button type="button" onclick="generateResetModalPass()" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">🎲 Generate</button>
                </div>
                <input type="text" id="resetModalNewPass" class="form-control" placeholder="Enter new password" style="font-family: monospace; font-weight: 600;">
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end;">
                <button type="button" onclick="closeWorkerResetPassModal()" class="btn btn-outline">Cancel</button>
                <button type="button" onclick="submitWorkerResetPassword()" class="btn btn-success">✓ Save New Password</button>
            </div>
            <div id="resetModalMsg" style="display: none; padding: 10px; border-radius: 8px; font-size: 0.85rem; margin-top: 12px;"></div>
        </div>
    </div>

    
    <!-- Global Modal: Super Admin Reset Shop Owner Password -->
    <div id="superAdminResetModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 99999; justify-content: center; align-items: center;" onclick="if(event.target===this) closeSuperAdminResetModal();">
        <div style="background: white; border-radius: 16px; padding: 24px; max-width: 440px; width: 92%; box-shadow: 0 12px 40px rgba(0,0,0,0.3); position: relative;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 0.9rem; font-weight: 800; color: var(--primary); text-transform: uppercase;">🔑 Reset Shop Owner Password</span>
                <button onclick="closeSuperAdminResetModal()" style="background: none; border: none; font-size: 1.4rem; cursor: pointer; color: #64748B;">✕</button>
            </div>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 14px;">
                Reset credentials for Shop Owner <strong id="resetTargetOwnerName" style="color: var(--primary);"></strong> (<code id="resetTargetOwnerUser" style="color: var(--secondary);"></code>).
            </p>
            <div class="form-group" style="margin-bottom: 14px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label style="margin: 0; font-weight: 700; font-size: 0.85rem;">New Password *</label>
                    <button type="button" onclick="generateResetOwnerPass()" class="btn btn-sm btn-outline" style="padding: 2px 8px; font-size: 0.72rem;">🎲 Generate</button>
                </div>
                <input type="text" id="resetOwnerNewPassword" class="form-control" placeholder="Enter new password" style="font-family: monospace; font-weight: 600;">
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end;">
                <button type="button" onclick="closeSuperAdminResetModal()" class="btn btn-outline">Cancel</button>
                <button type="button" onclick="submitResetOwnerPassword()" class="btn btn-success">✓ Save New Password</button>
            </div>
        </div>
    </div>

    <!-- Global Modal: Super Admin Edit Shop Owner Details -->
    <div id="superAdminEditModal" style="display: none; position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.65); z-index: 99999; justify-content: center; align-items: center;" onclick="if(event.target===this) closeSuperAdminEditModal();">
        <div style="background: white; border-radius: 16px; padding: 24px; max-width: 520px; width: 92%; box-shadow: 0 12px 40px rgba(0,0,0,0.3); position: relative; max-height: 90vh; overflow-y: auto;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;">
                <span style="font-size: 0.95rem; font-weight: 800; color: var(--primary); text-transform: uppercase;">✏️ Edit Shop Owner Account Details</span>
                <button onclick="closeSuperAdminEditModal()" style="background: none; border: none; font-size: 1.4rem; cursor: pointer; color: #64748B;">✕</button>
            </div>
            <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 14px;">
                Update account details for <strong id="editOwnerUsernameLabel" style="color: var(--primary);"></strong>.
            </p>
            <input type="hidden" id="editOwnerUsername">
            <div class="form-group" style="margin-bottom: 12px;">
                <label style="font-weight: 700; font-size: 0.85rem;">Owner Full Name *</label>
                <input type="text" id="editOwnerFullName" class="form-control" required>
            </div>
            <div class="form-group" style="margin-bottom: 12px;">
                <label style="font-weight: 700; font-size: 0.85rem;">Store / Shop Name *</label>
                <input type="text" id="editOwnerShopName" class="form-control" required>
            </div>
            <div class="form-group" style="margin-bottom: 12px;">
                <label style="font-weight: 700; font-size: 0.85rem;">Mobile Number (10 Digits) *</label>
                <input type="tel" id="editOwnerPhone" class="form-control" maxlength="10" required>
            </div>
            <div class="form-group" style="margin-bottom: 12px;">
                <label style="font-weight: 700; font-size: 0.85rem;">Owner Gmail Address *</label>
                <input type="email" id="editOwnerEmail" class="form-control" required>
            </div>
            <div class="form-group" style="margin-bottom: 12px;">
                <label style="font-weight: 700; font-size: 0.85rem;">Shop Code / ID *</label>
                <input type="text" id="editOwnerShopCode" class="form-control" required style="font-family: monospace;">
            </div>
            <div class="form-group" style="margin-bottom: 16px;">
                <label style="font-weight: 700; font-size: 0.85rem;">Shop Address &amp; City *</label>
                <input type="text" id="editOwnerAddress" class="form-control" required>
            </div>
            <div style="display: flex; gap: 8px; justify-content: flex-end;">
                <button type="button" onclick="closeSuperAdminEditModal()" class="btn btn-outline">Cancel</button>
                <button type="button" onclick="submitEditOwner()" class="btn" style="background: var(--primary); color: white; font-weight: 700;">✓ Save Changes</button>
            </div>
        </div>
    </div>

    <!-- Hidden File Input for Store Brand Logo Upload -->
    <input type="file" id="shopLogoUploadInput" accept="image/png, image/jpeg, image/jpg, image/webp" style="display: none;" onchange="handleShopLogoUpload(event)">

    <footer style="text-align: center; padding: 20px; color: var(--text-muted); font-size: 0.85rem; border-top: 1px solid var(--border);">
        Smart Bazaar Ecosystem &bull; Python / Django REST API &bull; PhonePe Flutter Android Engine
    </footer>

    <script>
        let productsData = {products_json};
        let workersData = {workers_json};
        let shopOwnersData = {shop_owners_json};
        let customersData = {customers_json};
        const recentSalesData = {recent_sales_json};
        const shopInfo = {shop_info_json};
        const shopsData = {shops_json};

        let currentRole = null;
        let cart = [];
        let attachedCustomer = null;

        // Active Store & Cashier context
        let activeShop = shopInfo;
        let activeShopOwner = {{ name: '{shop_info["owner_name"]}', phone: '{shop_info["owner_phone"]}' }};
        let currentCashierName = 'Arun Kumar';
        let currentCashierId = 'SB-EMP-001';

        function setActiveShopContext(shopOrCode) {{
            let shop = null;
            if (typeof shopOrCode === 'string') {{
                shop = shopsData.find(s => s.code === shopOrCode || s.owner_username === shopOrCode || (s.name && s.name.toLowerCase() === shopOrCode.toLowerCase()));
            }} else if (shopOrCode && typeof shopOrCode === 'object') {{
                shop = shopOrCode;
            }}
            if (!shop) {{
                const ownerRec = shopOwnersData.find(o => o.shop_code === shopOrCode || o.username === shopOrCode || o.owner_id === shopOrCode || o.login_id === shopOrCode);
                if (ownerRec) {{
                    shop = {{
                        name: ownerRec.shop_name,
                        code: ownerRec.shop_code,
                        owner_name: ownerRec.name,
                        owner_phone: ownerRec.phone,
                        address: ownerRec.address,
                        city: ownerRec.city || 'Kolkata',
                        phone: ownerRec.phone,
                        database_name: ownerRec.database_name,
                        db_status: ownerRec.db_status || 'ACTIVE',
                        logo_url: ''
                    }};
                }}
            }}
            if (!shop) {{
                shop = shopsData[0] || {{
                    name: 'Smart Bazaar Branch A',
                    code: 'SB-SHOP-001',
                    city: 'Kolkata',
                    address: '12 Salt Lake Sector V, Kolkata - 700091',
                    phone: '9830112231',
                    upi_vpa: 'smartbazaar@okaxis',
                    owner_name: 'Rahul Sharma',
                    owner_phone: '9830112231',
                    owner_username: 'OWNER001',
                    database_name: 'SmartBazaar_Shop_001',
                    db_status: 'ACTIVE',
                    logo_url: ''
                }};
            }}

            activeShop = shop;
            activeShopOwner = {{ name: shop.owner_name || 'Store Owner', phone: shop.owner_phone || '9692276657' }};

            // 1. Update Shop Owner Control Center Header
            const storeNameEl = document.getElementById('ownerStoreName');
            const storeCodeEl = document.getElementById('ownerStoreCode');
            const ownerNameEl = document.getElementById('ownerDisplayName');
            const ownerPhoneEl = document.getElementById('ownerDisplayPhone');
            const storeAddrEl = document.getElementById('ownerDisplayAddress');
            const storeCityEl = document.getElementById('ownerDisplayCity');
            const logoImg = document.getElementById('shopLogoHeaderImg');
            const logoPlaceholder = document.getElementById('shopLogoPlaceholder');
            const dbBadge = document.getElementById('shopDbBadge');

            if (storeNameEl) storeNameEl.innerText = shop.name;
            if (storeCodeEl) storeCodeEl.innerText = shop.code;
            if (ownerNameEl) ownerNameEl.innerText = shop.owner_name || 'Shop Owner';
            if (ownerPhoneEl) ownerPhoneEl.innerText = shop.owner_phone || 'N/A';
            if (storeAddrEl) storeAddrEl.innerText = shop.address || shop.city || 'Kolkata';
            if (storeCityEl) storeCityEl.innerText = shop.city || 'Kolkata';
            if (dbBadge) {{
                const dbName = shop.database_name || ('SmartBazaar_Shop_' + (shop.code ? shop.code.split('-').pop() : '001'));
                dbBadge.innerText = '🗄️ Database: ' + dbName + ' [ACTIVE]';
            }}

            if (logoImg && logoPlaceholder) {{
                if (shop.logo_url) {{
                    logoImg.src = shop.logo_url;
                    logoImg.style.display = 'block';
                    logoPlaceholder.style.display = 'none';
                }} else {{
                    logoImg.style.display = 'none';
                    logoPlaceholder.style.display = 'inline';
                }}
            }}

            // 2. Update POS Terminal Store Header
            const posShopName = document.getElementById('posCurrentShopName');
            const posShopCode = document.getElementById('posCurrentShopCode');
            if (posShopName) posShopName.innerText = shop.name;
            if (posShopCode) posShopCode.innerText = shop.code;

            // 3. Compute and Render Isolated 7 KPI Metrics (Requirement 2 & 4)
            const targetCode = activeShop.code;
            const shopProds = productsData.filter(p => p.shop_code === targetCode);
            const shopEmps = workersData.filter(w => w.shop_code === targetCode);
            const shopSales = recentSalesData.filter(s => s.shop_code === targetCode);

            const totalRev = shopSales.reduce((acc, s) => acc + (parseFloat(s.final_total) || 0), 0);
            const totalStock = shopProds.reduce((acc, p) => acc + (parseFloat(p.stock) || 0), 0);
            const lowStockCount = shopProds.filter(p => (parseFloat(p.stock) || 0) < LOW_STOCK_THRESHOLD).length;
            const shopCusts = (customersData || []).filter(c => c.shop_code === targetCode || c.shop_id === activeShop.id || (!c.shop_code && !c.shop_id));

            if (document.getElementById('kpiShopProducts')) document.getElementById('kpiShopProducts').innerText = shopProds.length;
            if (document.getElementById('kpiShopEmployees')) document.getElementById('kpiShopEmployees').innerText = shopEmps.length;
            if (document.getElementById('kpiShopCustomers')) document.getElementById('kpiShopCustomers').innerText = shopCusts.length;
            if (document.getElementById('tabCustCountBadge')) document.getElementById('tabCustCountBadge').innerText = shopCusts.length;
            if (document.getElementById('storeCustCountBadge')) document.getElementById('storeCustCountBadge').innerText = shopCusts.length;
            if (document.getElementById('kpiShopSales')) document.getElementById('kpiShopSales').innerText = '₹' + totalRev.toFixed(2);
            if (document.getElementById('kpiShopTransactions')) document.getElementById('kpiShopTransactions').innerText = shopSales.length;
            if (document.getElementById('kpiShopInventory')) document.getElementById('kpiShopInventory').innerText = totalStock;
            if (document.getElementById('kpiShopLowStock')) document.getElementById('kpiShopLowStock').innerText = lowStockCount;
            if (document.getElementById('adminLowStockCount')) document.getElementById('adminLowStockCount').innerText = lowStockCount;

            // First-Time Setup Wizard visibility (Requirement 4)
            const setupCard = document.getElementById('adminFirstTimeSetupCard');
            if (setupCard) {{
                setupCard.style.display = (shopProds.length === 0 && shopEmps.length === 0) ? 'block' : 'none';
            }}

            // 4. Render Isolated Tables and Forms
            renderAdminProducts();
            renderAdminWorkers();
            renderAdminCustomers();
            renderAdminSales();
            populateStoreSettingsForm();
        }}

        function switchLoginTab(tab) {{
            const staffBtn = document.getElementById('staffTabBtn');
            const custBtn = document.getElementById('customerTabBtn');
            const staffFm = document.getElementById('staffForm');
            const custFm = document.getElementById('customerForm');
            if (staffBtn) staffBtn.classList.toggle('active', tab === 'staff');
            if (custBtn) custBtn.classList.toggle('active', tab === 'customer');
            if (staffFm) staffFm.style.display = tab === 'staff' ? 'block' : 'none';
            if (custFm) custFm.style.display = tab === 'customer' ? 'block' : 'none';
        }}

        function togglePasswordVisibility(inputId, btn) {{
            const el = document.getElementById(inputId);
            if (!el) return;
            if (el.type === 'password') {{
                el.type = 'text';
                btn.textContent = '🙈';
            }} else {{
                el.type = 'password';
                btn.textContent = '👁️';
            }}
        }}

        // ======================= SUPER ADMIN: SHOP OWNERS & GMAIL OTP SYSTEM =======================
        // ======================= SUPER ADMIN: SHOP OWNERS & MULTI-STORE MANAGEMENT =======================
        function renderSuperAdminOwners(filteredList = null) {{
            const tbody = document.getElementById('superAdminOwnersTbody');
            if (!tbody) return;
            const countEl = document.getElementById('superAdminOwnerCount');
            const statTotal = document.getElementById('statTotalShops');
            const statActive = document.getElementById('statActiveShops');
            const statInactive = document.getElementById('statInactiveShops');

            const list = filteredList || shopOwnersData;
            if (countEl) countEl.innerText = list.length;
            if (statTotal) statTotal.innerText = shopOwnersData.length;
            if (statActive) statActive.innerText = shopOwnersData.filter(o => o.is_active).length;
            if (statInactive) statInactive.innerText = shopOwnersData.filter(o => !o.is_active).length;

            if (list.length === 0) {{
                tbody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: #94A3B8; padding: 24px;">No shop owners found matching search criteria.</td></tr>`;
                return;
            }}

            tbody.innerHTML = list.map(o => `
                <tr>
                    <td>
                        <div style="font-weight: 800; font-size: 0.95rem; color: #1E293B;">${{o.name || o.username}}</div>
                        <div style="font-size: 0.75rem; color: #64748B; font-family: monospace; font-weight: 600;">ID: ${{o.owner_id || o.username}}</div>
                    </td>
                    <td>
                        <strong style="color: var(--primary); font-size: 0.92rem;">${{o.shop_name || 'Store'}}</strong>
                        <div style="font-size: 0.75rem; color: #64748B; font-family: monospace; font-weight: 700;">Code: ${{o.shop_code || 'SB-SHOP'}}</div>
                        <div style="font-size: 0.72rem; color: #94A3B8;">${{o.city || 'Kolkata'}}</div>
                    </td>
                    <td>
                        <div style="font-weight: 600;">${{o.phone || 'N/A'}}</div>
                    </td>
                    <td>
                        <span style="font-family: monospace; font-size: 0.82rem;">${{o.email}}</span>
                        <div style="margin-top: 3px;">
                            ${{o.is_verified ? '<span class="badge badge-green" style="font-size: 0.7rem; padding: 2px 7px;">✓ Gmail Verified</span>' : '<span class="badge badge-amber" style="font-size: 0.7rem; padding: 2px 7px;">Pending OTP</span>'}}
                        </div>
                    </td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <span class="code-badge" style="background: #F1F5F9; padding: 3px 8px; border-radius: 6px; font-family: monospace; font-weight: 700; color: var(--primary); font-size: 0.82rem;">${{o.username}}</span>
                            <button type="button" onclick="navigator.clipboard.writeText('${{o.username}}'); alert('Copied ID: ${{o.username}}')" style="background: none; border: none; cursor: pointer; font-size: 0.85rem;" title="Copy Login ID">📋</button>
                        </div>
                        <div style="font-size: 0.72rem; color: #64748B; font-family: monospace; margin-top: 2px;">Pass: <code>${{o.password || 'OwnerPass@123'}}</code></div>
                    </td>
                    <td>
                        ${{o.is_active ? '<span class="badge badge-green">ACTIVE &amp; APPROVED</span>' : '<span class="badge badge-danger">SUSPENDED</span>'}}
                    </td>
                    <td style="text-align: right; white-space: nowrap;">
                        <button type="button" onclick="openEditOwnerModal('${{o.username}}')" class="btn btn-sm btn-outline" style="border-color: #CBD5E1; color: #334155; font-size: 0.76rem; padding: 5px 8px;" title="Edit Account Details">✏️ Edit</button>
                        <button type="button" onclick="openResetOwnerPasswordModal('${{o.username}}', '${{(o.name || o.username).replace(/'/g, "\\'")}}' )" class="btn btn-sm btn-outline" style="border-color: #CBD5E1; color: #334155; font-size: 0.76rem; padding: 5px 8px; margin-left: 3px;">🔑 Password</button>
                        <button type="button" onclick="toggleOwnerStatus('${{o.username}}')" class="btn btn-sm ${{o.is_active ? 'btn-danger' : 'btn-success'}}" style="font-size: 0.76rem; padding: 5px 8px; margin-left: 3px;">${{o.is_active ? '⛔ Suspend' : '✅ Activate'}}</button>
                        <button type="button" onclick="openStoreAsOwner('${{o.username}}')" class="btn btn-sm" style="background: var(--primary); color: white; font-size: 0.76rem; padding: 5px 9px; margin-left: 3px;">🚀 View Store</button>
                    </td>
                </tr>
            `).join('');
        }}

        function filterSuperAdminOwners() {{
            const query = (document.getElementById('searchOwnerInput')?.value || '').trim().toLowerCase();
            if (!query) {{
                renderSuperAdminOwners();
                return;
            }}
            const filtered = shopOwnersData.filter(o =>
                (o.name && o.name.toLowerCase().includes(query)) ||
                (o.username && o.username.toLowerCase().includes(query)) ||
                (o.shop_name && o.shop_name.toLowerCase().includes(query)) ||
                (o.shop_code && o.shop_code.toLowerCase().includes(query)) ||
                (o.phone && o.phone.includes(query)) ||
                (o.email && o.email.toLowerCase().includes(query))
            );
            renderSuperAdminOwners(filtered);
        }}

        function autoSuggestShopCode(force = false) {{
            const codeInput = document.getElementById('ownerShopCode');
            if (!codeInput) return;
            if (codeInput.value.trim() && !force) return;
            const nextNum = shopOwnersData.length + 1;
            codeInput.value = `SB-SHOP-${{String(nextNum).padStart(3, '0')}}`;
        }}

        function quickCreateShopOwnerDirect() {{
            const name = document.getElementById('ownerFullName').value.trim();
            const shopName = document.getElementById('ownerShopName').value.trim();
            const phone = document.getElementById('ownerPhone').value.trim();
            const email = document.getElementById('ownerGmail').value.trim();
            if (!name || !shopName || !phone || !email) {{
                alert('Please enter Owner Full Name, Shop Name, Phone Number, and Gmail address first.');
                return;
            }}
            document.getElementById('ownerOtpInput').value = '';
            document.getElementById('ownerOtpInput').focus();
            sendOwnerOtp();
        }}

        function openEditOwnerModal(username) {{
            const owner = shopOwnersData.find(o => o.username === username);
            if (!owner) return;
            document.getElementById('editOwnerUsernameLabel').innerText = `${{owner.name}} (${{owner.username}})`;
            document.getElementById('editOwnerUsername').value = owner.username;
            document.getElementById('editOwnerFullName').value = owner.name || '';
            document.getElementById('editOwnerShopName').value = owner.shop_name || '';
            document.getElementById('editOwnerPhone').value = owner.phone || '';
            document.getElementById('editOwnerEmail').value = owner.email || '';
            document.getElementById('editOwnerShopCode').value = owner.shop_code || '';
            document.getElementById('editOwnerAddress').value = owner.address || (owner.city + ', West Bengal');
            document.getElementById('superAdminEditModal').style.display = 'flex';
        }}

        function closeSuperAdminEditModal() {{
            document.getElementById('superAdminEditModal').style.display = 'none';
        }}

        async function submitEditOwner() {{
            const username = document.getElementById('editOwnerUsername').value;
            const name = document.getElementById('editOwnerFullName').value.trim();
            const shopName = document.getElementById('editOwnerShopName').value.trim();
            const phone = document.getElementById('editOwnerPhone').value.trim();
            const email = document.getElementById('editOwnerEmail').value.trim();
            const shopCode = document.getElementById('editOwnerShopCode').value.trim();
            const address = document.getElementById('editOwnerAddress').value.trim();

            if (!name || !shopName || !phone || !email) {{
                alert('All required fields must be filled.');
                return;
            }}

            try {{
                const res = await fetch('/api/superadmin/owners/edit/', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{ username, name, shop_name: shopName, phone, email, shop_code: shopCode, address }})
                }});
                const data = await res.json();
                if (data.success) {{
                    const owner = shopOwnersData.find(o => o.username === username);
                    if (owner) {{
                        owner.name = name;
                        owner.shop_name = shopName;
                        owner.phone = phone;
                        owner.email = email;
                        owner.shop_code = shopCode;
                        owner.address = address;
                    }}
                    renderSuperAdminOwners();
                    closeSuperAdminEditModal();
                    alert('✓ Shop Owner account details updated successfully!');
                }} else {{
                    alert('Failed to update: ' + (data.error || 'Server error.'));
                }}
            }} catch (e) {{
                alert('Error: ' + e.message);
            }}
        }}

        function autoSuggestOwnerLogin(force) {{
            const name = document.getElementById('ownerFullName').value.trim();
            const email = document.getElementById('ownerGmail').value.trim();
            const userIn = document.getElementById('ownerUsername');
            if (!userIn) return;
            if (!force && userIn.dataset.customEdited === 'true') return;

            let base = '';
            if (name) {{
                base = name.toLowerCase().replace(/[^a-z0-9]/g, '_').slice(0, 15);
            }} else if (email) {{
                base = email.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '_').slice(0, 15);
            }}
            if (base) {{
                userIn.value = 'owner_' + base.replace(/^owner_/, '');
            }}
        }}

        function generateOwnerPassword() {{
            const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789@#$';
            let pass = 'Owner@';
            for (let i = 0; i < 6; i++) {{
                pass += chars.charAt(Math.floor(Math.random() * chars.length));
            }}
            const el = document.getElementById('ownerPassword');
            if (el) el.value = pass;
        }}

        let activeOwnerVerificationId = null;
        let ownerOtpCountdownTimer = null;

        function startOwnerOtpCountdown(seconds = 60) {{
            const btn = document.getElementById('btnSendOwnerOtp');
            if (!btn) return;
            btn.disabled = true;
            let rem = seconds;
            if (ownerOtpCountdownTimer) clearInterval(ownerOtpCountdownTimer);
            ownerOtpCountdownTimer = setInterval(() => {{
                rem--;
                if (rem <= 0) {{
                    clearInterval(ownerOtpCountdownTimer);
                    btn.disabled = false;
                    btn.innerHTML = '🔄 Resend Verification OTP';
                }} else {{
                    btn.innerHTML = `⏳ Resend in ${{rem}}s`;
                }}
            }}, 1000);
        }}

        async function sendShopOwnerOtp() {{
            const name = (document.getElementById('ownerFullName') ? document.getElementById('ownerFullName').value : '').trim();
            const email = (document.getElementById('ownerGmail') ? document.getElementById('ownerGmail').value : '').trim();
            const phone = (document.getElementById('ownerPhone') ? document.getElementById('ownerPhone').value : '').trim();
            const shopName = (document.getElementById('ownerShopName') ? document.getElementById('ownerShopName').value : '').trim();
            const username = (document.getElementById('ownerUsername') ? document.getElementById('ownerUsername').value : '').trim();
            const addrEl = document.getElementById('ownerShopAddress') || document.getElementById('ownerAddress');
            const address = (addrEl ? addrEl.value : '').trim();
            const password = (document.getElementById('ownerPassword') ? document.getElementById('ownerPassword').value : '').trim();

            if (!name || !email || !phone || !shopName) {{
                alert('Please enter Shop Owner Full Name, Store Name, Phone Number, and Gmail address.');
                return;
            }}
            if (!email.toLowerCase().includes('@')) {{
                alert('Please enter a valid Gmail address.');
                return;
            }}

            const btn = document.getElementById('btnSendOwnerOtp');
            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = '<span>⏳ Sending OTP via Gmail API...</span>';
            }}

            try {{
                const res = await fetch('/api/super-admin/owners/send-otp', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        full_name: name,
                        name: name,
                        owner_name: name,
                        shop_name: shopName,
                        shop_code: (document.getElementById('ownerShopId') ? document.getElementById('ownerShopId').value.trim() : ''),
                        phone_number: phone,
                        phone: phone,
                        email: email,
                        username: username,
                        shop_address: address,
                        address: address,
                        password: password
                    }})
                }});
                const data = await res.json();
                if (data.success) {{
                    activeOwnerVerificationId = data.verification_id;
                    document.getElementById('ownerOtpTargetEmail').innerText = email;
                    document.getElementById('ownerOtpVerifyBox').style.display = 'block';
                    startOwnerOtpCountdown(data.resend_cooldown || 60);
                    document.getElementById('ownerOtpInput').value = '';
                    document.getElementById('ownerOtpInput').focus();
                    alert(`✓ Verification OTP successfully dispatched to ${{email}} via official Gmail API!\nPlease check your Gmail inbox and enter the 6-digit code manually below.`);
                }} else {{
                    alert('Error sending OTP: ' + (data.error || 'Failed to dispatch Gmail API message.'));
                    if (btn) {{
                        btn.disabled = false;
                        btn.innerHTML = '✉️ Send Gmail Verification OTP';
                    }}
                }}
            }} catch (err) {{
                alert('Network connection error: ' + err.message);
                if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '✉️ Send Gmail Verification OTP';
                }}
            }}
        }}

        async function verifyAndCreateShopOwner() {{
            const name = (document.getElementById('ownerFullName') ? document.getElementById('ownerFullName').value : '').trim();
            const shopName = (document.getElementById('ownerShopName') ? document.getElementById('ownerShopName').value : '').trim();
            const phone = (document.getElementById('ownerPhone') ? document.getElementById('ownerPhone').value : '').trim();
            const email = (document.getElementById('ownerGmail') ? document.getElementById('ownerGmail').value : '').trim();
            const username = (document.getElementById('ownerUsername') ? document.getElementById('ownerUsername').value : '').trim() || ('owner_' + name.toLowerCase().replace(/[^a-z0-9]/g, '_'));
            const password = (document.getElementById('ownerPassword') ? document.getElementById('ownerPassword').value : '').trim() || 'OwnerPass@123';
            const addrEl = document.getElementById('ownerShopAddress') || document.getElementById('ownerAddress');
            const address = (addrEl ? addrEl.value : '').trim();
            const otp = (document.getElementById('ownerOtpInput') ? document.getElementById('ownerOtpInput').value : '').trim();

            if (!otp || otp.length < 6) {{
                alert('Please enter the 6-digit verification code received on Gmail.');
                return;
            }}

            const btn = document.getElementById('btnVerifyCreateOwner');
            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = '⏳ Provisioning DB & Sending Activation Email...';
            }}

            try {{
                const res = await fetch('/api/super-admin/owners/create', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{
                        verification_id: activeOwnerVerificationId,
                        otp: otp,
                        full_name: name,
                        name: name,
                        owner_name: name,
                        shop_name: shopName,
                        shop_code: (document.getElementById('ownerShopId') ? document.getElementById('ownerShopId').value.trim() : ''),
                        phone_number: phone,
                        phone: phone,
                        email: email,
                        username: username,
                        password: password,
                        shop_address: address,
                        address: address
                    }})
                }});
                const data = await res.json();
                if (data.success) {{
                    const newOwner = {{
                        user_id: data.owner_id || 'ID',
                        owner_id: data.owner_id,
                        login_id: data.login_id,
                        username: data.login_id,
                        name: data.owner_name || name,
                        phone: phone,
                        email: email,
                        shop_name: data.shop_name || shopName,
                        shop_id: data.shop_id,
                        shop_code: data.shop_id,
                        database_name: `SmartBazaar_Shop_${{data.shop_id.replace(/[^0-9]/g, '').padStart(3, '0')}}`,
                        database_alias: `shop_${{data.shop_id.replace(/[^0-9]/g, '').padStart(3, '0')}}`,
                        db_status: 'ACTIVE',
                        city: 'Kolkata',
                        is_verified: true,
                        is_active: true,
                        status: 'APPROVED',
                        password: password,
                        joined: 'Today'
                    }};
                    shopOwnersData.unshift(newOwner);
                    renderSuperAdminOwners();
                    alert(`✅ STORE PROVISIONED & ACTIVATED!\n\nShop Owner "${{name}}" has verified via Gmail OTP.\nStore: ${{newOwner.shop_name}} (${{newOwner.shop_id}})\nOwner ID: ${{newOwner.owner_id}}\nLogin ID: ${{newOwner.login_id}}\nTemporary Password: ${{password}}\n\nAn official account activation email has been delivered to ${{email}} via Gmail API.`);
                    
                    document.getElementById('ownerFullName').value = '';
                    document.getElementById('ownerShopName').value = '';
                    document.getElementById('ownerPhone').value = '';
                    document.getElementById('ownerGmail').value = '';
                    document.getElementById('ownerUsername').value = '';
                    document.getElementById('ownerPassword').value = '';
                    if (document.getElementById('ownerAddress')) document.getElementById('ownerAddress').value = '';
                    if (document.getElementById('ownerShopAddress')) document.getElementById('ownerShopAddress').value = '';
                    document.getElementById('ownerOtpInput').value = '';
                    document.getElementById('ownerOtpVerifyBox').style.display = 'none';
                    activeOwnerVerificationId = null;
                }} else {{
                    alert('Error creating Shop Owner: ' + (data.error || 'Verification failed.'));
                }}
            }} catch (err) {{
                alert('Connection error: ' + err.message);
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '⚡ Verify OTP &amp; Provision Dedicated Store';
                }}
            }}
        }}

        let activeResetOwnerUsername = null;
        function openResetOwnerPasswordModal(username, name) {{
            activeResetOwnerUsername = username;
            document.getElementById('resetTargetOwnerName').innerText = name;
            document.getElementById('resetTargetOwnerUser').innerText = username;
            document.getElementById('resetOwnerNewPassword').value = 'Owner@' + Math.floor(1000 + Math.random() * 9000);
            document.getElementById('superAdminResetModal').style.display = 'flex';
        }}
        function closeSuperAdminResetModal() {{
            document.getElementById('superAdminResetModal').style.display = 'none';
            activeResetOwnerUsername = null;
        }}
        function generateResetOwnerPass() {{
            document.getElementById('resetOwnerNewPassword').value = 'Owner@' + Math.floor(100000 + Math.random() * 900000);
        }}
        async function submitResetOwnerPassword() {{
            if (!activeResetOwnerUsername) return;
            const newPass = document.getElementById('resetOwnerNewPassword').value.trim();
            if (!newPass || newPass.length < 6) {{
                alert('Password must be at least 6 characters.');
                return;
            }}
            try {{
                const res = await fetch('/api/superadmin/owners/reset-password/', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{username: activeResetOwnerUsername, new_password: newPass}})
                }});
                const data = await res.json();
                if (data.success) {{
                    alert(`✅ Password updated successfully for Shop Owner ${{activeResetOwnerUsername}}!\nNew Password: ${{newPass}}`);
                    closeSuperAdminResetModal();
                }} else {{
                    alert('Error resetting password: ' + (data.error || 'Server error.'));
                }}
            }} catch (err) {{
                alert('Error: ' + err.message);
            }}
        }}
        async function toggleOwnerStatus(username) {{
            try {{
                const res = await fetch('/api/superadmin/owners/toggle-status/', {{
                    method: 'POST',
                    headers: {{'Content-Type': 'application/json'}},
                    body: JSON.stringify({{username}})
                }});
                const data = await res.json();
                if (data.success) {{
                    const owner = shopOwnersData.find(o => o.username === username);
                    if (owner) owner.is_active = data.is_active;
                    renderSuperAdminOwners();
                }}
            }} catch (e) {{
                console.error(e);
            }}
        }}
        function openStoreAsOwner(username) {{
            const owner = shopOwnersData.find(o => o.username === username);
            const shop = shopsData.find(s => s.owner_username === username || (owner && s.code === owner.shop_code)) || {{
                name: owner ? owner.shop_name : 'Smart Bazaar Store',
                code: owner ? owner.shop_code : 'SB-SHOP-NEW',
                city: owner ? owner.city : 'Kolkata',
                address: owner ? owner.address : 'Station Road, Kolkata - 700001',
                phone: owner ? owner.phone : '9692276657',
                upi_vpa: 'smartbazaar@okaxis',
                owner_name: owner ? owner.name : username,
                owner_username: username,
                owner_phone: owner ? owner.phone : '9692276657',
                status: 'APPROVED',
                logo_url: ''
            }};
            currentRole = 'SHOP_OWNER';
            updateRoleBasedVisibility('SHOP_OWNER');
            setActiveShopContext(shop);
            setAuthUser(`${{shop.owner_name}} (${{username}})`, 'Store Admin', 'badge-purple', 'adminView');
            switchAdminSection('products');
        }}

        function switchToStoreView() {{
            setAuthUser('Super Admin', 'Platform Super Admin', 'badge-purple', 'superAdminView');
            renderSuperAdminOwners();
        }}

        function openOwnerBillingTerminal() {{
            currentRole = 'SHOP_OWNER';
            currentCashierName = activeShop.owner_name || 'Store Owner';
            currentCashierId = 'OWNER-' + (activeShop.code || '001');
            setAuthUser(`${{activeShop.owner_name}} (Owner POS)`, '👑 Store Owner', 'badge-purple', 'workerPosView');
            const cashierLabel = document.getElementById('posCurrentCashierName');
            const cashierIdEl = document.getElementById('posCurrentCashierId');
            if (cashierLabel) cashierLabel.innerText = `${{activeShop.owner_name}} (Owner)`;
            if (cashierIdEl) cashierIdEl.innerText = currentCashierId;
            initPos();
        }}

        function focusAddProductForm() {{
            switchAdminSection('products');
            const inp = document.getElementById('newProdName');
            if (inp) {{
                inp.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                setTimeout(() => inp.focus(), 300);
            }}
        }}

        function focusAddWorkerForm() {{
            switchAdminSection('workers');
            const inp = document.getElementById('workerFullName');
            if (inp) {{
                inp.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                setTimeout(() => inp.focus(), 300);
            }}
        }}

        function populateStoreSettingsForm() {{
            if (!activeShop) return;
            const nameInp = document.getElementById('settStoreName');
            const codeInp = document.getElementById('settStoreCode');
            const badgeEl = document.getElementById('settStoreCodeBadge');
            const ownerNameInp = document.getElementById('settOwnerName');
            const ownerPhoneInp = document.getElementById('settOwnerPhone');
            const phoneInp = document.getElementById('settStorePhone');
            const cityInp = document.getElementById('settStoreCity');
            const addrInp = document.getElementById('settStoreAddress');
            const upiInp = document.getElementById('settStoreUpi');

            if (nameInp) nameInp.value = activeShop.name || '';
            if (codeInp) codeInp.value = activeShop.code || '';
            if (badgeEl) badgeEl.innerText = activeShop.code || '';
            if (ownerNameInp) ownerNameInp.value = activeShop.owner_name || '';
            if (ownerPhoneInp) ownerPhoneInp.value = activeShop.owner_phone || '';
            if (phoneInp) phoneInp.value = activeShop.phone || '';
            if (cityInp) cityInp.value = activeShop.city || '';
            if (addrInp) addrInp.value = activeShop.address || '';
            if (upiInp) upiInp.value = activeShop.upi_vpa || 'smartbazaar@okaxis';
        }}

        async function saveStoreProfileSettings() {{
            const name = document.getElementById('settStoreName')?.value.trim();
            const address = document.getElementById('settStoreAddress')?.value.trim();
            const city = document.getElementById('settStoreCity')?.value.trim();
            const phone = document.getElementById('settStorePhone')?.value.trim();
            const upi_vpa = document.getElementById('settStoreUpi')?.value.trim();
            const msgEl = document.getElementById('storeSettingsMsg');

            try {{
                const res = await fetch('/api/admin/shop/update-profile/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{
                        shop_code: activeShop.code,
                        owner_username: activeShop.owner_username,
                        name,
                        address,
                        city,
                        phone,
                        upi_vpa
                    }})
                }});
                const data = await res.json();
                if (data.success) {{
                    activeShop.name = name;
                    activeShop.address = address;
                    activeShop.city = city;
                    activeShop.phone = phone;
                    activeShop.upi_vpa = upi_vpa;

                    const match = shopsData.find(s => s.code === activeShop.code);
                    if (match) Object.assign(match, {{ name, address, city, phone, upi_vpa }});

                    setActiveShopContext(activeShop);

                    if (msgEl) {{
                        msgEl.style.display = 'block';
                        msgEl.style.background = '#DCFCE7';
                        msgEl.style.color = '#15803D';
                        msgEl.innerText = '✓ Store Profile and Billing Settings updated successfully!';
                        setTimeout(() => {{ msgEl.style.display = 'none'; }}, 4000);
                    }}
                }} else {{
                    alert('Error updating profile: ' + (data.error || 'Server error'));
                }}
            }} catch (e) {{
                alert('Request failed: ' + e.message);
            }}
        }}

        function switchAdminSection(section) {{
            document.getElementById('tabBtnProducts')?.classList.toggle('active', section === 'products');
            document.getElementById('tabBtnWorkers')?.classList.toggle('active', section === 'workers');
            document.getElementById('tabBtnCustomers')?.classList.toggle('active', section === 'customers');
            document.getElementById('tabBtnReports')?.classList.toggle('active', section === 'reports');
            document.getElementById('tabBtnSettings')?.classList.toggle('active', section === 'settings');

            const secProd = document.getElementById('adminSectionProducts');
            const secWork = document.getElementById('adminSectionWorkers');
            const secCust = document.getElementById('adminSectionCustomers');
            const secRepo = document.getElementById('adminSectionReports');
            const secSett = document.getElementById('adminSectionSettings');

            if (secProd) secProd.style.display = section === 'products' ? 'block' : 'none';
            if (secWork) secWork.style.display = section === 'workers' ? 'block' : 'none';
            if (secCust) secCust.style.display = section === 'customers' ? 'block' : 'none';
            if (secRepo) secRepo.style.display = section === 'reports' ? 'block' : 'none';
            if (secSett) secSett.style.display = section === 'settings' ? 'block' : 'none';

            if (section === 'customers') renderAdminCustomers();
            if (section === 'reports') renderAdminSales();
            if (section === 'settings') populateStoreSettingsForm();
        }}

        function updateRoleBasedVisibility(role) {{
            const isSuperAdmin = (role === 'SUPER_ADMIN');
            const headerBtn = document.getElementById('superAdminHeaderLogoBtn');
            const brandCard = document.getElementById('superAdminBrandCard');
            const storeBadge = document.getElementById('adminStoreBadge');
            const addProdCard = document.getElementById('addProductCard');
            const superNotice = document.getElementById('superAdminProductNotice');

            if (headerBtn) headerBtn.style.display = isSuperAdmin ? 'inline-flex' : 'none';
            if (brandCard) brandCard.style.display = isSuperAdmin ? 'block' : 'none';
            if (addProdCard) addProdCard.style.display = isSuperAdmin ? 'none' : 'block';
            if (superNotice) superNotice.style.display = isSuperAdmin ? 'block' : 'none';
            if (storeBadge) {{
                storeBadge.innerText = isSuperAdmin ? '🛡️ Super Admin Control Active' : '👑 Store Admin Active';
            }}
        }}

        function loginAsWorker(name, workerId, role = 'CASHIER') {{
            currentRole = 'WORKER';
            updateRoleBasedVisibility('WORKER');
            // Set header badge and exclusively open workerPosView
            setAuthUser(`${{name}} (${{workerId}})`, `👷 ${{role}}`, 'badge-green', 'workerPosView');
            
            // Automatically update POS Terminal Cashier name
            const cashierLabel = document.getElementById('posCurrentCashierName');
            if (cashierLabel) {{
                cashierLabel.innerText = `${{name}} (${{workerId}})`;
            }}
            
            // Initialize POS terminal scanner, cart and low stock monitor
            initPos();
        }}

        function showView(viewId) {{
            // Strict Role-Based Access Control: Worker can only access workerPosView
            if (currentRole === 'WORKER' && viewId === 'adminView') {{
                alert('⛔ Access Denied: Cashier/Worker accounts have permission ONLY for the Worker / Cashier POS Billing Terminal.');
                return;
            }}

            document.querySelectorAll('.view-section').forEach(el => el.classList.remove('active'));
            document.getElementById(viewId).classList.add('active');

            const isAuth = viewId !== 'loginView';
            document.getElementById('userHeaderBadge').style.display = isAuth ? 'flex' : 'none';
            document.getElementById('guestHeaderBadge').style.display = isAuth ? 'none' : 'flex';
            const mobileLogout = document.getElementById('headerLogoutBtnMobile');
            const desktopLogout = document.getElementById('headerLogoutBtnDesktop');
            if (mobileLogout) mobileLogout.style.display = isAuth ? 'inline-flex' : 'none';
            if (desktopLogout) desktopLogout.style.display = isAuth ? 'inline-flex' : 'none';
            if (typeof renderMobileBottomNav === 'function') {{
                renderMobileBottomNav(currentRole);
            }}
        }}

        function quickLogin(username, password, role) {{
            document.getElementById('staffUsername').value = username;
            document.getElementById('staffPassword').value = password;
            if (role === 'SUPER_ADMIN' || username === 'admin') {{
                currentRole = 'SUPER_ADMIN';
                updateRoleBasedVisibility('SUPER_ADMIN');
                setAuthUser('Super Admin', 'Platform Super Admin', 'badge-purple', 'superAdminView');
                renderSuperAdminOwners();
            }} else if (role === 'SHOP_OWNER' || username === 'owner_grocery') {{
                currentRole = 'SHOP_OWNER';
                const ownerRec = shopOwnersData.find(o => o.login_id === username || o.owner_id === username || o.shop_name === username || o.username === username);
                const ownerShop = ownerRec ? (shopsData.find(s => s.code === ownerRec.shop_id || s.name === ownerRec.shop_name) || {{
                    name: ownerRec.shop_name,
                    code: ownerRec.shop_id,
                    owner_name: ownerRec.owner_name || ownerRec.name,
                    owner_phone: ownerRec.phone,
                    address: ownerRec.address,
                    city: 'Kolkata'
                }}) : shopInfo;
                setActiveShopContext(ownerShop);
                updateRoleBasedVisibility('SHOP_OWNER');
                setAuthUser(ownerShop.owner_name || 'Shop Owner', `👑 Store Admin (${{ownerShop.code}})`, 'badge-purple', 'adminView');
                switchAdminSection('products');
            }} else if (role === 'WORKER' || username.startsWith('cashier') || username.startsWith('worker')) {{
                updateRoleBasedVisibility('WORKER');
                const w = workersData.find(item => item.worker_id === username || item.employee_id === username || item.name === username);
                const name = w ? w.name : (username === 'cashier_arun' ? 'Arun Kumar' : username);
                if (w && w.shop_code) {{
                    setActiveShopContext(w.shop_code);
                }}
                loginAsWorker(name, username, w ? w.role : 'CASHIER');
            }} else {{
                handleStaffLogin();
            }}
        }}

        function quickCustomerLogin(email, otp) {{
            setAuthUser('Rahul Sharma', 'Customer', 'badge-amber', 'customerView');
            renderCustomerBills();
        }}

        async function handleStaffLogin() {{
            const u = document.getElementById('staffUsername').value.trim();
            const p = document.getElementById('staffPassword').value;
            const err = document.getElementById('staffError');
            err.style.display = 'none';

            if (!u || !p) {{
                err.innerText = "Please enter both username/worker ID and password.";
                err.style.display = 'block';
                return;
            }}

            // 1. Super Admin role — opens Super Admin Control Center exclusively
            if (u === 'admin' && (p === 'AdminPass@123' || p === 'Admin@123')) {{
                currentRole = 'SUPER_ADMIN';
                updateRoleBasedVisibility('SUPER_ADMIN');
                setAuthUser('Super Admin', 'Platform Super Admin', 'badge-purple', 'superAdminView');
                renderSuperAdminOwners();
                return;
            }}

            // 2. Default Shop Owner demo
            if ((u === 'owner_grocery' && (p === 'OwnerPass@123' || p === 'Owner@123')) ||
                (u.toLowerCase() === 'owner' && (p === 'OwnerPass@123' || p === 'Owner@123'))) {{
                currentRole = 'SHOP_OWNER';
                setActiveShopContext(shopInfo);
                updateRoleBasedVisibility('SHOP_OWNER');
                setAuthUser('Shop Owner', `👑 Store Admin (${{shopInfo.code}})`, 'badge-purple', 'adminView');
                switchAdminSection('products');
                return;
            }}

            // 3. Dynamic check for any Shop Owner registered via Super Admin
            const matchedOwner = shopOwnersData.find(o => (
                (o.username && o.username.toLowerCase() === u.toLowerCase()) ||
                (o.login_id && o.login_id.toLowerCase() === u.toLowerCase()) ||
                (o.owner_id && o.owner_id.toLowerCase() === u.toLowerCase()) ||
                (o.email && o.email.toLowerCase() === u.toLowerCase()) ||
                o.phone === u
            ));
            if (matchedOwner) {{
                if (!matchedOwner.is_active) {{
                    err.innerText = "Store Suspended: This shop account has been deactivated by Super Admin.";
                    err.style.display = 'block';
                    return;
                }}
                if ((matchedOwner.password && p === matchedOwner.password) || p === 'OwnerPass@123' || p === 'Owner@123') {{
                    currentRole = 'SHOP_OWNER';
                    const targetCode = matchedOwner.shop_code || matchedOwner.shop_id;
                    const ownerShop = shopsData.find(s => s.code === targetCode || s.name === matchedOwner.shop_name) || {{
                        name: matchedOwner.shop_name,
                        code: targetCode,
                        owner_name: matchedOwner.name || matchedOwner.owner_name,
                        owner_phone: matchedOwner.phone,
                        address: matchedOwner.address,
                        city: matchedOwner.city || 'Kolkata',
                        database_name: matchedOwner.database_name,
                        db_status: matchedOwner.db_status || 'ACTIVE'
                    }};
                    setActiveShopContext(ownerShop);
                    updateRoleBasedVisibility('SHOP_OWNER');
                    setAuthUser(`${{ownerShop.owner_name || matchedOwner.name}}`, `👑 Store Admin (${{ownerShop.code}})`, 'badge-purple', 'adminView');
                    switchAdminSection('products');
                    return;
                }}
            }} 
            
            // 4. Default Cashier demo (cashier_arun)
            if (u === 'cashier_arun' && (p === 'CashierPass@123' || p === 'Cashier@123')) {{
                setActiveShopContext('SB-SHOP-001');
                loginAsWorker('Arun Kumar', 'cashier_arun', 'CASHIER');
                return;
            }}

            // 5. Dynamic check for any worker added by Shop Owner
            const matchedWorker = workersData.find(w => (
                (w.worker_id && w.worker_id.toLowerCase() === u.toLowerCase()) ||
                (w.employee_id && w.employee_id.toLowerCase() === u.toLowerCase()) ||
                (w.email && w.email.toLowerCase() === u.toLowerCase()) ||
                (w.name && w.name.toLowerCase() === u.toLowerCase()) ||
                w.phone === u
            ));
            if (matchedWorker) {{
                if (!matchedWorker.is_active) {{
                    err.innerText = "Access Revoked: Your worker account has been disabled by the Store Admin.";
                    err.style.display = 'block';
                    return;
                }}
                if ((matchedWorker.password && p === matchedWorker.password) || p === 'CashierPass@123' || p === 'WorkerPass@123' || p === 'StaffPass@123') {{
                    if (matchedWorker.shop_code) {{
                        setActiveShopContext(matchedWorker.shop_code);
                    }}
                    loginAsWorker(matchedWorker.name, matchedWorker.worker_id || matchedWorker.name, matchedWorker.role);
                    return;
                }}
            }}

            // 6. Try backend authentication API (/api/auth/staff/login/)
            try {{
                const res = await fetch('/api/auth/staff/login/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ username: u, password: p }})
                }});
                const data = await res.json();
                if (res.ok && data.user) {{
                    const role = data.role;
                    const name = data.user.first_name || data.user.username;
                    if (role === 'SUPER_ADMIN') {{
                        currentRole = 'SUPER_ADMIN';
                        updateRoleBasedVisibility('SUPER_ADMIN');
                        setAuthUser(name, 'Super Admin', 'badge-purple', 'superAdminView');
                        renderSuperAdminOwners();
                    }} else if (role === 'SHOP_OWNER') {{
                        currentRole = 'SHOP_OWNER';
                        const ownerShop = data.shop || (shopsData.find(s => s.code === data.shop_code || s.id === data.shop_id) || shopInfo);
                        setActiveShopContext(ownerShop);
                        updateRoleBasedVisibility('SHOP_OWNER');
                        setAuthUser(ownerShop.owner_name || name, `👑 Store Admin (${{ownerShop.code}})`, 'badge-purple', 'adminView');
                        switchAdminSection('products');
                    }} else if (role === 'WORKER') {{
                        updateRoleBasedVisibility('WORKER');
                        if (data.shop && data.shop.code) {{
                            setActiveShopContext(data.shop);
                        }} else if (data.shop_code) {{
                            setActiveShopContext(data.shop_code);
                        }}
                        loginAsWorker(name, data.user.username, data.role_in_shop || 'CASHIER');
                    }}
                    return;
                }} else {{
                    err.innerText = data.error || "Invalid username/worker ID or password.";
                    err.style.display = 'block';
                }}
            }} catch (e) {{
                err.innerText = "Invalid credentials. Please verify your Worker Login ID and password.";
                err.style.display = 'block';
            }}
        }}

        let activeCustomerLoginVerificationId = null;

        async function handleSendCustomerOtp() {{
            const email = document.getElementById('customerEmail').value.trim();
            const err = document.getElementById('customerError');
            err.style.display = 'none';

            if (!email.includes('@')) {{
                err.innerText = "Please enter a valid Gmail address.";
                err.style.display = 'block';
                return;
            }}

            const btn = document.getElementById('sendOtpBtn');
            if (btn) {{
                btn.disabled = true;
                btn.innerText = "Sending Code...";
            }}

            try {{
                const res = await fetch('/api/shop/customers/send-otp', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ email: email, full_name: 'Customer', phone_number: '9831098310' }})
                }});
                const data = await res.json();
                if (data.success) {{
                    activeCustomerLoginVerificationId = data.verification_id;
                    document.getElementById('otpGroup').style.display = 'block';
                    document.getElementById('sendOtpBtn').style.display = 'none';
                    document.getElementById('verifyOtpBtn').style.display = 'block';
                    document.getElementById('customerOtp').value = '';
                    document.getElementById('customerOtp').focus();
                }} else {{
                    err.innerText = data.error || "Failed to dispatch Gmail verification code.";
                    err.style.display = 'block';
                    if (btn) {{
                        btn.disabled = false;
                        btn.innerText = "Send OTP to Gmail";
                    }}
                }}
            }} catch (e) {{
                err.innerText = "Connection error: " + e.message;
                err.style.display = 'block';
                if (btn) {{
                    btn.disabled = false;
                    btn.innerText = "Send OTP to Gmail";
                }}
            }}
        }}

        async function handleVerifyCustomerOtp() {{
            const email = document.getElementById('customerEmail').value.trim();
            const otp = document.getElementById('customerOtp').value.trim();
            const err = document.getElementById('customerError');
            err.style.display = 'none';

            if (!otp || otp.length < 6) {{
                err.innerText = "Please enter the 6-digit code received on your Gmail.";
                err.style.display = 'block';
                return;
            }}

            try {{
                const res = await fetch('/api/shop/customers/verify-otp', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        verification_id: activeCustomerLoginVerificationId,
                        email: email,
                        otp: otp
                    }})
                }});
                const data = await res.json();
                if (data.success) {{
                    setAuthUser('Verified Customer', 'Customer', 'badge-amber', 'customerView');
                    renderCustomerBills();
                }} else {{
                    err.innerText = data.error || "Invalid verification code.";
                    err.style.display = 'block';
                }}
            }} catch (e) {{
                err.innerText = "Verification error: " + e.message;
                err.style.display = 'block';
            }}
        }}

        function setAuthUser(name, roleLabel, badgeClass, viewId) {{
            document.getElementById('userNameBadge').innerText = name;
            const rBadge = document.getElementById('userRoleBadge');
            rBadge.innerText = roleLabel;
            rBadge.className = 'badge ' + badgeClass;
            showView(viewId);
        }}

        function logout() {{
            currentRole = null;
            updateRoleBasedVisibility(null);
            cart = [];
            showView('loginView');
            if (typeof renderMobileBottomNav === 'function') {{
                renderMobileBottomNav(null);
            }}
        }}

        // ======================= AUTOMATIC LOW-STOCK (< 15) NOTIFICATIONS =======================
        const LOW_STOCK_THRESHOLD = 15;
        let knownLowStockIds = new Set();

        function showLowStockToast(items) {{
            if (!items || items.length === 0) return;
            const toast = document.getElementById('lowStockToast');
            if (!toast) return;
            const summaryHtml = items.slice(0, 3).map(it =>
                `<div style="margin-top: 4px; font-size: 0.84rem;">• <strong>${{it.name}}</strong>: <strong style="color:#DC2626;">${{it.stock}} ${{it.unit}}</strong> left (&lt; 15)</div>`
            ).join('') + (items.length > 3 ? `<div style="font-size:0.78rem; margin-top:4px;">+ ${{items.length - 3}} more product(s) below 15</div>` : '');

            toast.innerHTML = `
                <div style="display: flex; justify-content: space-between; align-items: flex-start; gap: 10px;">
                    <div>
                        <div style="font-weight: 800; font-size: 0.92rem; color: #991B1B;">🔔 Automatic Low-Stock Alert (&lt; 15)</div>
                        <div style="font-size: 0.76rem; color: #92400E;">Notified Shop Owner &amp; Worker/Cashier Dashboards:</div>
                        ${{summaryHtml}}
                    </div>
                    <button type="button" onclick="document.getElementById('lowStockToast').style.display='none'" style="background: none; border: none; font-size: 1.1rem; cursor: pointer; color: #78350F;">✕</button>
                </div>
            `;
            toast.style.display = 'block';
            clearTimeout(window._lowStockToastTimer);
            window._lowStockToastTimer = setTimeout(() => {{ toast.style.display = 'none'; }}, 7000);
        }}

        function scrollToAdminLowStock() {{
            const panel = document.getElementById('adminLowStockPanel');
            if (panel && panel.style.display !== 'none') {{
                panel.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }} else {{
                alert('All products currently have 15 or more units in stock.');
            }}
        }}

        function toggleWorkerLowStockPanel() {{
            const panel = document.getElementById('workerLowStockPanel');
            if (!panel) return;
            const lowItems = productsData.filter(p => parseFloat(p.stock) < LOW_STOCK_THRESHOLD);
            if (lowItems.length === 0) {{
                alert('All products currently have 15 or more units in stock.');
                return;
            }}
            panel.style.display = panel.style.display === 'none' ? 'block' : 'block';
            panel.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
        }}

        function renderLowStockNotifications(triggerToastForNew = false) {{
            const lowItems = productsData
                .filter(p => parseFloat(p.stock) < LOW_STOCK_THRESHOLD)
                .sort((a, b) => parseFloat(a.stock) - parseFloat(b.stock));

            const newlyTriggered = [];
            const currentIds = new Set();
            lowItems.forEach(p => {{
                const sid = String(p.id);
                currentIds.add(sid);
                if (triggerToastForNew && !knownLowStockIds.has(sid)) {{
                    newlyTriggered.push(p);
                }}
            }});
            knownLowStockIds = currentIds;

            // Update Admin / Shop Owner Bell & Panel
            const adminCountEl = document.getElementById('adminLowStockCount');
            const adminHeadEl = document.getElementById('adminLowStockHeadlineCount');
            const adminBellBtn = document.getElementById('adminNotifBellBtn');
            const adminPanel = document.getElementById('adminLowStockPanel');
            const adminList = document.getElementById('adminLowStockList');

            if (adminCountEl) adminCountEl.innerText = lowItems.length;
            if (adminHeadEl) adminHeadEl.innerText = lowItems.length;
            if (adminBellBtn) {{
                if (lowItems.length > 0) {{
                    adminBellBtn.style.background = '#FEF2F2';
                    adminBellBtn.style.color = '#B91C1C';
                    adminBellBtn.style.borderColor = '#FCA5A5';
                }} else {{
                    adminBellBtn.style.background = '#F1F5F9';
                    adminBellBtn.style.color = '#334155';
                    adminBellBtn.style.borderColor = '#CBD5E1';
                }}
            }}
            if (adminPanel && adminList) {{
                if (lowItems.length === 0) {{
                    adminPanel.style.display = 'none';
                    adminList.innerHTML = '';
                }} else {{
                    adminPanel.style.display = 'block';
                    adminList.innerHTML = lowItems.map(p => {{
                        const isZero = parseFloat(p.stock) <= 0;
                        return `
                            <div style="background: white; border: 1.5px solid ${{isZero ? '#FCA5A5' : '#FCD34D'}}; border-radius: 10px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center; gap: 8px;">
                                <div>
                                    <div style="font-weight: 700; font-size: 0.86rem; color: #1E293B;">${{p.name}}</div>
                                    <div style="font-size: 0.74rem; color: #64748B;"><code>${{p.barcode}}</code> &bull; ${{p.category}}</div>
                                    <span class="badge ${{isZero ? 'badge-red' : 'badge-amber'}}" style="margin-top: 4px;">
                                        ${{isZero ? '🚨 0 OUT OF STOCK' : '⚠️ Only ' + p.stock + ' ' + p.unit + ' left (&lt; 15)'}}
                                    </span>
                                </div>
                                <button type="button" onclick="editProductPrompt('${{p.id}}', ${{p.selling_price}}, ${{p.stock}})" class="btn btn-sm" style="background: var(--primary); font-size: 0.74rem; padding: 5px 10px; white-space: nowrap;">
                                    ➕ Restock
                                </button>
                            </div>
                        `;
                    }}).join('');
                }}
            }}

            // Update Worker / Cashier Bell & Panel
            const workerCountEl = document.getElementById('workerLowStockCount');
            const workerHeadEl = document.getElementById('workerLowStockHeadlineCount');
            const workerBellBtn = document.getElementById('workerNotifBellBtn');
            const workerPanel = document.getElementById('workerLowStockPanel');
            const workerList = document.getElementById('workerLowStockList');

            if (workerCountEl) workerCountEl.innerText = lowItems.length;
            if (workerHeadEl) workerHeadEl.innerText = lowItems.length;
            if (workerBellBtn) {{
                if (lowItems.length > 0) {{
                    workerBellBtn.style.background = '#FEF2F2';
                    workerBellBtn.style.color = '#B91C1C';
                    workerBellBtn.style.borderColor = '#FCA5A5';
                }} else {{
                    workerBellBtn.style.background = '#F1F5F9';
                    workerBellBtn.style.color = '#334155';
                    workerBellBtn.style.borderColor = '#CBD5E1';
                }}
            }}
            if (workerPanel && workerList) {{
                if (lowItems.length === 0) {{
                    workerPanel.style.display = 'none';
                    workerList.innerHTML = '';
                }} else {{
                    workerPanel.style.display = 'block';
                    workerList.innerHTML = lowItems.map(p => {{
                        const isZero = parseFloat(p.stock) <= 0;
                        return `
                            <div style="background: white; border: 1.5px solid ${{isZero ? '#FCA5A5' : '#FCD34D'}}; border-radius: 8px; padding: 6px 10px; font-size: 0.8rem; display: inline-flex; align-items: center; gap: 6px;">
                                <span>${{isZero ? '🚨' : '⚠️'}}</span>
                                <strong>${{p.name}}</strong>
                                <span class="badge ${{isZero ? 'badge-red' : 'badge-amber'}}" style="padding: 2px 7px; font-size: 0.72rem;">
                                    ${{p.stock}} ${{p.unit}}
                                </span>
                            </div>
                        `;
                    }}).join('');
                }}
            }}

            if (triggerToastForNew && newlyTriggered.length > 0) {{
                showLowStockToast(newlyTriggered);
            }}
        }}

        async function syncLowStockAlertsFromServer(showToast = false) {{
            try {{
                const res = await fetch('/api/inventory/low-stock-alerts/');
                if (!res.ok) return;
                const data = await res.json();
                if (!data.alerts) return;

                let changed = false;
                data.alerts.forEach(al => {{
                    let p = productsData.find(item => String(item.id) === String(al.product_id));
                    if (p) {{
                        if (parseFloat(p.stock) !== parseFloat(al.current_stock)) {{
                            p.stock = al.current_stock;
                            changed = true;
                        }}
                    }} else {{
                        productsData.unshift({{
                            id: al.product_id,
                            name: al.product_name,
                            barcode: al.barcode,
                            selling_price: al.selling_price || 0,
                            mrp: al.selling_price || 0,
                            tax_rate: 5,
                            unit: al.unit || 'PCS',
                            stock: al.current_stock,
                            category: al.category || 'General'
                        }});
                        changed = true;
                    }}
                }});
                renderLowStockNotifications(showToast);
                if (changed) {{
                    const adminVisible = document.getElementById('adminView')?.classList.contains('active');
                    const posVisible = document.getElementById('workerPosView')?.classList.contains('active');
                    if (adminVisible) renderAdminProducts();
                    if (posVisible) renderPosGrid();
                }}
            }} catch (_) {{}}
        }}

        // ======================= ADMIN: PRODUCT OPERATIONS =======================
        function renderAdminProducts(filteredList = null) {{
            const shopProds = productsData.filter(p => p.shop_code === activeShop.code);
            const list = filteredList || shopProds;
            const tbody = document.getElementById('adminProductsTbody');
            const countBadge = document.getElementById('prodCountBadge');
            const emptyState = document.getElementById('adminProductsEmptyState');
            const tableWrap = document.getElementById('adminProductsTableWrapper');

            if (countBadge) countBadge.innerText = shopProds.length;
            if (tbody) tbody.innerHTML = '';

            renderLowStockNotifications(false);

            if (shopProds.length === 0) {{
                if (emptyState) emptyState.style.display = 'block';
                if (tableWrap) tableWrap.style.display = 'none';
                return;
            }} else {{
                if (emptyState) emptyState.style.display = 'none';
                if (tableWrap) tableWrap.style.display = 'block';
            }}

            if (list.length === 0) {{
                if (tbody) tbody.innerHTML = '<tr><td colspan="8" style="text-align: center; color: var(--text-muted); padding: 20px;">No matching products found.</td></tr>';
                return;
            }}

            list.forEach(p => {{
                const stockNum = parseFloat(p.stock);
                let statusBadge = '<span class="badge badge-green">IN STOCK</span>';
                let rowStyle = '';
                let stockColor = 'var(--success)';
                if (stockNum <= 0) {{
                    statusBadge = '<span class="badge badge-red">🚨 OUT OF STOCK</span>';
                    rowStyle = 'background: #FEF2F2;';
                    stockColor = 'var(--danger)';
                }} else if (stockNum < LOW_STOCK_THRESHOLD) {{
                    statusBadge = '<span class="badge badge-amber">⚠️ LOW STOCK (&lt;15)</span>';
                    rowStyle = 'background: #FFFBEB;';
                    stockColor = '#D97706';
                }}
                tbody.innerHTML += `
                    <tr style="${{rowStyle}}">
                        <td>
                            <div style="font-weight: 700; color: #1E293B;">${{p.name}}</div>
                            <span style="font-size: 0.75rem; color: var(--text-muted);">${{p.unit}} &bull; ${{p.category}}</span>
                        </td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="cursor: pointer; border: 1px solid var(--border); padding: 3px 6px; border-radius: 6px; background: white;" onclick="showBarcodeModal('${{p.id}}')" title="Click to view full scannable barcode">
                                    <img src="/api/products/barcode-image/${{p.barcode}}/?text=0" style="height: 26px; width: 68px; object-fit: contain; display: block;" alt="Barcode">
                                </div>
                                <div>
                                    <code style="font-size: 0.82rem; font-weight: 700;">${{p.barcode}}</code>
                                    <button onclick="showBarcodeModal('${{p.id}}')" class="btn btn-sm btn-outline" style="padding: 1px 6px; font-size: 0.7rem; display: block; margin-top: 2px;">
                                        📷 View Tag
                                    </button>
                                </div>
                            </div>
                        </td>
                        <td><span class="badge badge-purple">${{p.category}}</span></td>
                        <td><strong style="color: var(--primary);">₹${{p.selling_price.toFixed(2)}}</strong></td>
                        <td style="color: var(--text-muted);">₹${{p.mrp.toFixed(2)}}</td>
                        <td>
                            <strong style="font-size: 1rem; color: ${{stockColor}};">${{p.stock}}</strong> ${{p.unit}}
                        </td>
                        <td>${{statusBadge}}</td>
                        <td>
                            <div style="display: flex; gap: 6px;">
                                ${{currentRole === 'SUPER_ADMIN' 
                                    ? `<span style="font-size: 0.75rem; color: #94A3B8; font-weight: 600; padding: 4px 8px; background: #F1F5F9; border-radius: 6px;">🔒 Read-Only</span>` 
                                    : `<button onclick="editProductPrompt('${{p.id}}', ${{p.selling_price}}, ${{p.stock}})" class="btn btn-sm btn-outline">✏️ Edit</button>
                                       <button onclick="deleteProduct('${{p.id}}', '${{p.name}}')" class="btn btn-sm btn-danger">🗑️ Delete</button>`
                                }}
                            </div>
                        </td>
                    </tr>
                `;
            }});
        }}

        function filterAdminProducts() {{
            const q = document.getElementById('searchProductInput').value.toLowerCase().trim();
            const shopProds = productsData.filter(p => p.shop_code === activeShop.code);
            if (!q) {{
                renderAdminProducts();
                return;
            }}
            const filtered = shopProds.filter(p => 
                p.name.toLowerCase().includes(q) || 
                p.barcode.toLowerCase().includes(q) || 
                p.category.toLowerCase().includes(q)
            );
            renderAdminProducts(filtered);
        }}

        // ======================= BARCODE MODAL LOGIC =======================
        let activeModalBarcode = null;

        function showBarcodeModal(productId) {{
            console.log('showBarcodeModal called with:', productId);
            const p = productsData.find(item => String(item.id) === String(productId) || String(item.barcode) === String(productId));
            if (!p) {{
                console.warn('Product not found for id/barcode:', productId);
                return;
            }}
            activeModalBarcode = p.barcode;
            const titleEl = document.getElementById('modalProdTitle');
            if (titleEl) titleEl.innerText = p.name;
            const catEl = document.getElementById('modalProdCategory');
            if (catEl) catEl.innerText = (p.category || 'General') + ' • ' + (p.unit || 'PCS');

            const sp = parseFloat(p.selling_price) || 0;
            const mrp = parseFloat(p.mrp) || sp;
            const priceEl = document.getElementById('modalProdPrice');
            if (priceEl) priceEl.innerText = '₹' + sp.toFixed(2);
            const mrpEl = document.getElementById('modalProdMrp');
            if (mrpEl) mrpEl.innerText = 'MRP ₹' + mrp.toFixed(2);
            const stockEl = document.getElementById('modalProdStock');
            if (stockEl) stockEl.innerText = (p.stock != null ? p.stock : 500) + ' ' + (p.unit || 'PCS') + ' In Stock';

            // Clean 1D barcode image
            const imgEl = document.getElementById('modalBarcodeImg');
            if (imgEl) imgEl.src = `/api/products/barcode-image/${{encodeURIComponent(p.barcode)}}/?text=0`;
            const numEl = document.getElementById('modalBarcodeNum');
            if (numEl) numEl.innerText = p.barcode;
            const dlLink = document.getElementById('modalDownloadLink');
            if (dlLink) dlLink.href = `/api/products/barcode-image/${{encodeURIComponent(p.barcode)}}/?text=0&download=1`;

            const modal = document.getElementById('barcodeTagModal');
            if (modal) {{
                modal.style.display = 'flex';
            }}
        }}

        function closeBarcodeModal() {{
            const modal = document.getElementById('barcodeTagModal');
            if (modal) modal.style.display = 'none';
        }}

        function modalScanToPos() {{
            if (!activeModalBarcode) return;
            const code = activeModalBarcode;
            closeBarcodeModal();
            setAuthUser('Arun Kumar', 'Cashier', 'badge-green', 'workerPosView');
            initPos();
            continueAsGuest();
            setTimeout(() => {{
                simulateBarcodeScan(code);
            }}, 300);
        }}

        async function submitAddProduct() {{
            if (currentRole === 'SUPER_ADMIN') {{
                alert('⛔ Permission Denied: Super Admin does not have access to add products. Products must be added exclusively by the authorized Shop Owner.');
                return;
            }}
            if (currentRole !== 'SHOP_OWNER') {{
                alert('⛔ Permission Denied: Only authenticated Shop Owners can add products to the store.');
                return;
            }}
            const name = document.getElementById('newProdName').value.trim();
            const category = document.getElementById('newProdCategory').value.trim();
            const barcode = document.getElementById('newProdBarcode').value.trim();
            const price = parseFloat(document.getElementById('newProdPrice').value);
            const mrp = parseFloat(document.getElementById('newProdMrp').value);
            const qty = parseFloat(document.getElementById('newProdQty').value);
            const unit = document.getElementById('newProdUnit').value;
            const msgEl = document.getElementById('addProductMsg');

            try {{
                const res = await fetch('/api/admin/products/add/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{
                        name,
                        category_name: category,
                        barcode,
                        selling_price: price,
                        mrp,
                        quantity: qty,
                        unit,
                        caller_role: currentRole,
                        owner_username: activeShop?.owner_username || '',
                        shop_code: activeShop?.code || ''
                    }})
                }});
                let data = null;
                try {{
                    data = await res.json();
                }} catch (parseErr) {{
                    throw new Error('Server returned non-JSON response (HTTP ' + res.status + ')');
                }}
                if (data && data.success) {{
                    msgEl.style.display = 'block';
                    msgEl.style.background = '#DCFCE7';
                    msgEl.style.color = '#15803D';
                    msgEl.innerText = `✓ Product "${{name}}" with ${{qty}} ${{unit}} added successfully!`;
                    
                    productsData.unshift(data.product);
                    renderAdminProducts();
                    renderLowStockNotifications(true);
                    document.getElementById('addProductForm').reset();
                    document.getElementById('newProdQty').value = '50';
                    setTimeout(() => {{ msgEl.style.display = 'none'; }}, 3000);
                }} else {{
                    alert('Error adding product: ' + (data.error || 'Unknown error'));
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        async function deleteProduct(productId, prodName) {{
            if (currentRole === 'SUPER_ADMIN') {{
                alert('⛔ Permission Denied: Super Admin cannot delete products from store inventory.');
                return;
            }}
            if (!confirm(`Are you sure you want to delete "${{prodName}}"? This will remove it from the catalog and store inventory.`)) {{
                return;
            }}
            try {{
                const res = await fetch('/api/admin/products/delete/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ product_id: productId, caller_role: currentRole }})
                }});
                const data = await res.json();
                if (data.success) {{
                    productsData = productsData.filter(p => p.id !== productId);
                    renderAdminProducts();
                    renderLowStockNotifications(false);
                }} else {{
                    alert('Delete failed: ' + data.error);
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        async function editProductPrompt(productId, oldPrice, oldQty) {{
            if (currentRole === 'SUPER_ADMIN') {{
                alert('⛔ Permission Denied: Super Admin cannot modify store product details.');
                return;
            }}
            const newPriceStr = prompt("Enter new Selling Price (₹):", oldPrice);
            if (newPriceStr === null) return;
            const newQtyStr = prompt("Enter new Stock Quantity:", oldQty);
            if (newQtyStr === null) return;

            const newPrice = parseFloat(newPriceStr);
            const newQty = parseFloat(newQtyStr);

            if (isNaN(newPrice) || isNaN(newQty)) {{
                alert("Invalid numbers entered.");
                return;
            }}

            try {{
                const res = await fetch('/api/admin/products/update/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ product_id: productId, selling_price: newPrice, quantity: newQty, caller_role: currentRole }})
                }});
                const data = await res.json();
                if (data.success) {{
                    const p = productsData.find(item => item.id === productId);
                    if (p) {{
                        p.selling_price = newPrice;
                        p.stock = newQty;
                    }}
                    renderAdminProducts();
                    renderLowStockNotifications(true);
                }} else {{
                    alert('Update failed: ' + data.error);
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        // ======================= ADMIN: WORKER FORM VALIDATION & MANAGEMENT =======================
        function onWorkerPhoneInput(input) {{
            // Exact 10 digits only, strip non-digits
            let clean = input.value.replace(/[^0-9]/g, '');
            if (clean.length > 10) clean = clean.slice(0, 10);
            input.value = clean;

            const counter = document.getElementById('workerPhoneCounter');
            const feedback = document.getElementById('workerPhoneFeedback');
            if (counter) counter.innerText = `${{clean.length}}/10`;

            if (clean.length === 10) {{
                input.style.borderColor = '#16A34A';
                input.style.background = '#F0FDF4';
                if (feedback) {{
                    feedback.style.color = '#16A34A';
                    feedback.innerText = '✓ Valid 10-digit phone number (numbers only)';
                }}
            }} else {{
                input.style.borderColor = clean.length > 0 ? '#E11D48' : '';
                input.style.background = clean.length > 0 ? '#FFF1F2' : '';
                if (feedback) {{
                    feedback.style.color = clean.length > 0 ? '#E11D48' : 'var(--text-muted)';
                    feedback.innerText = clean.length === 0 
                        ? 'Exact 10 numerical digits only (no spaces or letters).' 
                        : `Needs ${{10 - clean.length}} more digit(s) (must be exact 10 digits).`;
                }}
            }}
            validateWorkerFormLive();
        }}

        function evaluatePasswordStrength(pass) {{
            const specialChars = "!@#$%^&*()_+-=[]{{}};:'\\",.<>/?~`";
            const res = {{
                score: 0,
                length: pass.length >= 8,
                hasUpper: /[A-Z]/.test(pass),
                hasLower: /[a-z]/.test(pass),
                hasNumber: /[0-9]/.test(pass),
                hasSpecial: specialChars.split('').some(s => pass.includes(s)),
                isStrong: false,
                msg: ''
            }};
            if (res.length) res.score += 25;
            if (res.hasUpper && res.hasLower) res.score += 25;
            if (res.hasNumber) res.score += 25;
            if (res.hasSpecial) res.score += 25;

            res.isStrong = (res.length && res.hasUpper && res.hasLower && res.hasNumber && res.hasSpecial);

            if (!pass) {{
                res.msg = '8+ chars with uppercase, lowercase, number & symbol.';
            }} else if (res.isStrong) {{
                res.msg = '✓ Strong password (Upper, Lower, Number & Symbol verified)';
            }} else {{
                const missing = [];
                if (!res.length) missing.push('8+ chars');
                if (!res.hasUpper) missing.push('uppercase (A-Z)');
                if (!res.hasLower) missing.push('lowercase (a-z)');
                if (!res.hasNumber) missing.push('number (0-9)');
                if (!res.hasSpecial) missing.push('special symbol (@, #, $, etc.)');
                res.msg = 'Missing: ' + missing.join(', ');
            }}
            return res;
        }}

        function onWorkerPasswordInput() {{
            const passInput = document.getElementById('newWorkerPassword');
            const confirmInput = document.getElementById('newWorkerConfirmPassword');
            const pass = passInput ? passInput.value : '';
            const confirm = confirmInput ? confirmInput.value : '';

            const strength = evaluatePasswordStrength(pass);
            const bar = document.getElementById('workerPassStrengthBar');
            const fill = document.getElementById('workerPassStrengthFill');
            const feedback = document.getElementById('workerPassFeedback');

            if (bar && fill) {{
                if (pass.length > 0) {{
                    bar.style.display = 'block';
                    fill.style.width = `${{strength.score}}%`;
                    if (strength.score <= 25) fill.style.background = '#EF4444';
                    else if (strength.score <= 50) fill.style.background = '#F59E0B';
                    else if (strength.score < 100) fill.style.background = '#3B82F6';
                    else fill.style.background = '#16A34A';
                }} else {{
                    bar.style.display = 'none';
                }}
            }}
            if (feedback) {{
                feedback.innerText = strength.msg;
                feedback.style.color = strength.isStrong ? '#16A34A' : (pass.length > 0 ? '#E11D48' : 'var(--text-muted)');
            }}
            if (passInput) {{
                passInput.style.borderColor = strength.isStrong ? '#16A34A' : (pass.length > 0 ? '#E11D48' : '');
            }}

            // Retype password match check
            const matchBadge = document.getElementById('workerPassMatchBadge');
            const confirmFeedback = document.getElementById('workerConfirmFeedback');
            if (confirmInput) {{
                if (!confirm) {{
                    confirmInput.style.borderColor = '';
                    confirmInput.style.background = '';
                    if (matchBadge) matchBadge.style.display = 'none';
                    if (confirmFeedback) {{
                        confirmFeedback.style.color = 'var(--text-muted)';
                        confirmFeedback.innerText = 'Must match the password entered above.';
                    }}
                }} else if (confirm === pass) {{
                    confirmInput.style.borderColor = '#16A34A';
                    confirmInput.style.background = '#F0FDF4';
                    if (matchBadge) {{
                        matchBadge.style.display = 'inline';
                        matchBadge.style.color = '#16A34A';
                        matchBadge.innerText = '✓ MATCHED';
                    }}
                    if (confirmFeedback) {{
                        confirmFeedback.style.color = '#16A34A';
                        confirmFeedback.innerText = '✓ Passwords match perfectly!';
                    }}
                }} else {{
                    confirmInput.style.borderColor = '#E11D48';
                    confirmInput.style.background = '#FFF1F2';
                    if (matchBadge) {{
                        matchBadge.style.display = 'inline';
                        matchBadge.style.color = '#E11D48';
                        matchBadge.innerText = '✗ MISMATCH';
                    }}
                    if (confirmFeedback) {{
                        confirmFeedback.style.color = '#E11D48';
                        confirmFeedback.innerText = '✗ Passwords do not match yet.';
                    }}
                }}
            }}
            validateWorkerFormLive();
        }}

        function toggleWorkerPassVisibility(inputId, btn) {{
            const el = document.getElementById(inputId);
            if (!el) return;
            if (el.type === 'password') {{
                el.type = 'text';
                if (btn) btn.innerText = '🔒';
            }} else {{
                el.type = 'password';
                if (btn) btn.innerText = '👁️';
            }}
        }}

        function autoSuggestWorkerId(force = false) {{
            const idInput = document.getElementById('newWorkerId');
            if (!idInput) return;
            if (idInput.value.trim() && !force) return;
            const name = document.getElementById('newWorkerName').value.trim();
            const role = document.getElementById('newWorkerRole').value;
            const prefix = role === 'CASHIER' ? 'cashier' : 'worker';
            if (name) {{
                const clean = name.toLowerCase().replace(/[^a-z0-9]/g, '_').replace(/_+/g, '_').replace(/^_|_$/g, '');
                idInput.value = `${{prefix}}_${{clean}}`;
            }} else {{
                const email = document.getElementById('newWorkerEmail').value.trim();
                if (email && email.includes('@')) {{
                    const handle = email.split('@')[0].toLowerCase().replace(/[^a-z0-9]/g, '_');
                    idInput.value = `${{prefix}}_${{handle}}`;
                }} else {{
                    const rand = Math.floor(100 + Math.random() * 900);
                    idInput.value = `${{prefix}}_${{rand}}`;
                }}
            }}
            validateWorkerFormLive();
        }}

        function generateRandomWorkerPassword() {{
            const passInput = document.getElementById('newWorkerPassword');
            const confirmInput = document.getElementById('newWorkerConfirmPassword');
            if (!passInput) return;

            const uppers = 'ABCDEFGHJKLMNPQRSTUVWXYZ';
            const lowers = 'abcdefghijkmnpqrstuvwxyz';
            const digits = '23456789';
            const specials = '!@#$%^&*';
            const prefixes = ['Bazaar', 'Cashier', 'Prime', 'Smart', 'Super', 'Retail'];
            
            const p = prefixes[Math.floor(Math.random() * prefixes.length)];
            const d = Math.floor(100 + Math.random() * 900);
            const s1 = specials[Math.floor(Math.random() * specials.length)];
            const s2 = specials[Math.floor(Math.random() * specials.length)];
            const u = uppers[Math.floor(Math.random() * uppers.length)];
            const l = lowers[Math.floor(Math.random() * lowers.length)];

            // Meets: length >= 8, uppercase, lowercase, number, special symbol
            const pass = `${{p}}${{s1}}${{d}}${{s2}}${{u}}${{l}}`;
            passInput.value = pass;
            if (confirmInput) {{
                confirmInput.value = pass; // Retype verified simultaneously
            }}
            onWorkerPasswordInput();
        }}

        function validateWorkerForm(showAlert = false) {{
            const name = document.getElementById('newWorkerName')?.value.trim() || '';
            const phone = document.getElementById('newWorkerPhone')?.value.trim() || '';
            const email = document.getElementById('newWorkerEmail')?.value.trim().toLowerCase() || '';
            const workerId = document.getElementById('newWorkerId')?.value.trim() || '';
            const password = document.getElementById('newWorkerPassword')?.value || '';
            const confirm = document.getElementById('newWorkerConfirmPassword')?.value || '';

            const alertBox = document.getElementById('workerPreValidationAlert');
            const alertText = document.getElementById('workerPreValidationAlertText');

            let error = null;

            if (!name || name.length < 2) {{
                error = 'Worker Full Name is required (minimum 2 characters).';
            }} else if (!phone || !/^[0-9]{{10}}$/.test(phone)) {{
                if (!phone) {{
                    error = 'Phone Number is required (exact 10 numerical digits only).';
                }} else if (phone.length !== 10) {{
                    error = `Phone Number must be exact 10 digits only (currently ${{phone.length}} digit${{phone.length > 1 ? 's' : ''}}). No letters or spaces allowed.`;
                }} else {{
                    error = 'Phone Number must contain digits only (0-9) and nothing else.';
                }}
            }} else if (!email || !email.includes('@') || !email.includes('.')) {{
                error = 'A valid Worker Gmail address is required (e.g. name@gmail.com).';
            }} else if (!workerId || workerId.length < 3) {{
                error = 'Unique Worker Login ID is required (minimum 3 characters).';
            }} else {{
                const strength = evaluatePasswordStrength(password);
                if (!strength.isStrong) {{
                    error = 'Strong Password required: minimum 8 characters with at least one uppercase letter, one lowercase letter, one number, and one special symbol (e.g. Cashier@2026#).';
                }} else if (!confirm) {{
                    error = 'Please retype password in the "VERIFY IT DOUBLE" field.';
                }} else if (password !== confirm) {{
                    error = 'Retyped password does not match! Both passwords must be identical.';
                }}
            }}

            if (error) {{
                if (showAlert) {{
                    if (alertBox && alertText) {{
                        alertText.innerText = error;
                        alertBox.style.display = 'flex';
                        alertBox.scrollIntoView({{ behavior: 'smooth', block: 'nearest' }});
                    }} else {{
                        alert(error);
                    }}
                }}
                return false;
            }}

            // All fields valid
            if (alertBox) alertBox.style.display = 'none';
            return true;
        }}

        function validateWorkerFormLive() {{
            const alertBox = document.getElementById('workerPreValidationAlert');
            if (alertBox && alertBox.style.display !== 'none') {{
                validateWorkerForm(false);
            }}
        }}

        function renderQuickAccessWorkers() {{
            const container = document.getElementById('quickAccessWorkerRows');
            if (!container) return;

            if (workersData.length === 0) {{
                container.innerHTML = `
                    <tr>
                        <td><span class="badge badge-green" style="font-size: 0.85rem; padding: 6px 14px;">👷 Worker / Cashier</span></td>
                        <td><strong style="font-size: 0.95rem; color: var(--primary);">cashier_arun</strong></td>
                        <td><code>CashierPass@123</code></td>
                        <td style="color: #334155; font-size: 0.88rem;">
                            POS billing terminal &mdash; exclusive worker access. Instant barcode scanner, itemized cart, assisted checkout.
                        </td>
                        <td style="text-align: right;">
                            <button onclick="quickLogin('cashier_arun', 'CashierPass@123', 'WORKER')" class="btn btn-sm" style="background: var(--success); color: white; padding: 8px 16px; font-weight: 700;">⚡ 1-Click Login</button>
                        </td>
                    </tr>
                `;
                return;
            }}

            container.innerHTML = workersData.map(w => {{
                const pass = w.password || 'CashierPass@123';
                const wId = w.worker_id || w.name;
                return `
                    <tr>
                        <td>
                            <span class="badge badge-green" style="font-size: 0.85rem; padding: 6px 14px;">👷 Worker / ${{w.role || 'Cashier'}}</span>
                            <div style="font-size: 0.75rem; color: #64748B; margin-top: 3px; font-weight: 600;">${{w.name}}</div>
                        </td>
                        <td><strong style="font-size: 0.95rem; color: var(--primary); font-family: monospace;">${{wId}}</strong></td>
                        <td><code style="background: #F1F5F9; padding: 2px 6px; border-radius: 4px; font-weight: 700;">${{pass}}</code></td>
                        <td style="color: #334155; font-size: 0.88rem;">
                            POS billing terminal &mdash; <strong>exclusive worker access</strong> for ${{w.name}} (${{w.phone}}). Auto-restricted to cashier checkout.
                        </td>
                        <td style="text-align: right;">
                            <button onclick="quickLogin('${{wId}}', '${{pass}}', 'WORKER')" class="btn btn-sm" style="background: var(--success); color: white; padding: 8px 16px; font-weight: 700;">⚡ 1-Click Login</button>
                        </td>
                    </tr>
                `;
            }}).join('');
        }}

        function renderAdminWorkers() {{
            const activeCode = (activeShop && activeShop.code) ? activeShop.code : 'SB-SHOP-001';
            const filteredWorkers = workersData.filter(w => w.shop_code === activeCode);

            const tbody = document.getElementById('adminWorkersTbody');
            const countBadge = document.getElementById('workerCountBadge');
            const emptyEl = document.getElementById('adminWorkersEmptyState');
            const wrapperEl = document.getElementById('adminWorkersTableWrapper');
            const kpiEmps = document.getElementById('kpiShopEmployees');

            if (countBadge) countBadge.innerText = filteredWorkers.length;
            if (kpiEmps) kpiEmps.innerText = filteredWorkers.length;

            if (filteredWorkers.length === 0) {{
                if (emptyEl) emptyEl.style.display = 'block';
                if (wrapperEl) wrapperEl.style.display = 'none';
                if (tbody) tbody.innerHTML = '';
                return;
            }}

            if (emptyEl) emptyEl.style.display = 'none';
            if (wrapperEl) wrapperEl.style.display = 'block';
            if (!tbody) return;
            tbody.innerHTML = '';

            filteredWorkers.forEach(w => {{
                const statusBadge = w.is_active 
                    ? '<span class="badge badge-green">ACCESS GRANTED</span>'
                    : '<span class="badge badge-red">ACCESS REVOKED</span>';
                const toggleBtnText = w.is_active ? '🔒 Revoke' : '🔓 Grant';
                const toggleBtnClass = w.is_active ? 'btn-danger' : 'btn-success';
                const workerId = w.worker_id || w.name.toLowerCase().replace(/[ ]+/g, '_');
                const empIdBadge = w.employee_id ? `<span class="badge badge-blue" style="font-size: 0.72rem; margin-left: 4px;">${{w.employee_id}}</span>` : '';

                tbody.innerHTML += `
                    <tr>
                        <td>
                            <div style="display: flex; align-items: center; gap: 10px;">
                                ${{w.logo ? `<img src="${{w.logo}}" style="width: 36px; height: 36px; border-radius: 50%; object-fit: cover; border: 2px solid var(--primary); flex-shrink: 0;" alt="${{w.name}}">` : `<div style="width: 36px; height: 36px; border-radius: 50%; background: #DCFCE7; color: var(--primary); display: flex; align-items: center; justify-content: center; font-weight: 800; font-size: 0.95rem; flex-shrink: 0;">${{(w.name || 'W').charAt(0).toUpperCase()}}</div>`}}
                                <div>
                                    <strong style="color: #0F172A; font-size: 0.94rem;">${{w.name}}</strong>
                                    ${{empIdBadge}}
                                    <div style="font-size: 0.73rem; color: #64748B;">Staff Member &bull; ${{w.shop_name || (activeShop ? activeShop.name : 'Store')}}</div>
                                </div>
                            </div>
                        </td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 6px;">
                                <code style="font-weight: 800; color: #0F5132; background: #DCFCE7; padding: 4px 8px; border-radius: 6px; font-size: 0.82rem; font-family: monospace;">${{workerId}}</code>
                                <button onclick="navigator.clipboard.writeText('${{workerId}}'); alert('Copied ID: ${{workerId}}');" class="btn btn-sm btn-outline" style="padding: 2px 6px; font-size: 0.72rem;" title="Copy Unique ID">📋</button>
                            </div>
                        </td>
                        <td>${{w.phone}}</td>
                        <td><code>${{w.email}}</code> <span class="badge badge-purple" style="font-size: 0.7rem;">✓ Verified</span></td>
                        <td><span class="badge badge-blue">${{w.role}}</span></td>
                        <td>${{statusBadge}}</td>
                        <td>
                            <div style="display: flex; gap: 6px; flex-wrap: wrap;">
                                <button onclick="openWorkerResetPassModal('${{w.user_id}}', '${{w.name}}', '${{workerId}}')" class="btn btn-sm btn-outline" style="color: #4338CA; border-color: #A5B4FC;" title="Reset Login Password">🔑 Password</button>
                                <button onclick="toggleWorkerAccess('${{w.user_id}}')" class="btn btn-sm ${{toggleBtnClass}}">${{toggleBtnText}}</button>
                                <button onclick="deleteWorker('${{w.user_id}}', '${{w.name}}')" class="btn btn-sm btn-outline" style="color: var(--danger); border-color: var(--danger);">🗑️ Remove</button>
                            </div>
                        </td>
                    </tr>
                `;
            }});
        }}

        function renderAdminCustomers() {{
            if (!activeShop) return;
            const shopCode = activeShop.code || activeShop.shop_code;
            const shopId = activeShop.id || activeShop.shop_id;

            // Filter customers belonging to or associated with this shop
            const storeCusts = (customersData || []).filter(c => {{
                return (c.shop_code && c.shop_code === shopCode) ||
                       (c.shop_id && c.shop_id === shopId) ||
                       (!c.shop_code && !c.shop_id);
            }});

            const countBadge = document.getElementById('storeCustCountBadge');
            const tabBadge = document.getElementById('tabCustCountBadge');
            const kpiTop = document.getElementById('kpiShopCustomers');
            const secCusts = document.getElementById('kpiSectionStoreCusts');

            if (countBadge) countBadge.innerText = storeCusts.length;
            if (tabBadge) tabBadge.innerText = storeCusts.length;
            if (kpiTop) kpiTop.innerText = storeCusts.length;
            if (secCusts) secCusts.innerText = storeCusts.length;

            const totalSpend = storeCusts.reduce((sum, c) => sum + (parseFloat(c.total_spent) || 0), 0);
            const secSpend = document.getElementById('kpiSectionStoreSpend');
            if (secSpend) secSpend.innerText = '₹' + totalSpend.toFixed(2);

            const verifiedCount = storeCusts.filter(c => c.is_verified).length;
            const secVer = document.getElementById('kpiSectionVerifiedCusts');
            if (secVer) secVer.innerText = verifiedCount;

            const q = (document.getElementById('searchStoreCustInput')?.value || '').trim().toLowerCase();
            const filtered = q ? storeCusts.filter(c => {{
                return (c.name && c.name.toLowerCase().includes(q)) ||
                       (c.phone && c.phone.includes(q)) ||
                       (c.customer_code && c.customer_code.toLowerCase().includes(q)) ||
                       (c.email && c.email.toLowerCase().includes(q)) ||
                       (c.registered_by && c.registered_by.toLowerCase().includes(q));
            }}) : storeCusts;

            const tbody = document.getElementById('adminCustomersTbody');
            const emptyEl = document.getElementById('adminCustomersEmptyState');
            const tableWrap = document.getElementById('adminCustomersTableWrapper');

            if (!tbody) return;

            if (filtered.length === 0) {{
                if (emptyEl) emptyEl.style.display = 'block';
                if (tableWrap) tableWrap.style.display = 'none';
                tbody.innerHTML = '';
                return;
            }}

            if (emptyEl) emptyEl.style.display = 'none';
            if (tableWrap) tableWrap.style.display = 'block';

            tbody.innerHTML = filtered.map(c => {{
                const initials = (c.name || 'C').split(' ').map(w => w[0]).slice(0, 2).join('').toUpperCase();
                const workerBadge = c.registered_by ? 
                    `<span style="background: #F1F5F9; color: #1E293B; padding: 3px 8px; border-radius: 6px; font-size: 0.78rem; font-weight: 700; border: 1px solid #CBD5E1;">👤 ${{c.registered_by}}</span>` : 
                    `<span style="color: #94A3B8; font-size: 0.78rem;">Walk-in Checkout</span>`;

                return `
                    <tr>
                        <td><strong style="font-family: monospace; color: var(--primary); background: #DCFCE7; padding: 3px 8px; border-radius: 5px; font-size: 0.85rem;">${{c.customer_code || 'SB-CUST'}}</strong></td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 8px;">
                                <div style="width: 32px; height: 32px; border-radius: 50%; background: #E0E7FF; color: #4338CA; font-weight: 800; font-size: 0.78rem; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
                                    ${{initials}}
                                </div>
                                <div>
                                    <div style="font-weight: 700; color: var(--text-main); font-size: 0.90rem;">${{c.name}}</div>
                                    <div style="font-size: 0.75rem; color: #64748B;">Store Buyer</div>
                                </div>
                            </div>
                        </td>
                        <td><strong style="font-family: monospace; font-size: 0.90rem; color: #1E293B;">📱 ${{c.phone}}</strong></td>
                        <td>
                            <div style="display: flex; align-items: center; gap: 4px; font-size: 0.84rem;">
                                <span>${{c.email || 'N/A'}}</span>
                                <span style="color: #16A34A; font-weight: 800;" title="Gmail Verified">✓</span>
                            </div>
                        </td>
                        <td>${{workerBadge}}</td>
                        <td><span style="font-weight: 700; font-size: 0.88rem; color: #475569;">${{c.visit_count || 1}} visit(s)</span></td>
                        <td><strong style="color: #16A34A; font-size: 0.92rem;">₹${{(parseFloat(c.total_spent) || 0).toFixed(2)}}</strong></td>
                        <td><span class="badge badge-amber" style="font-weight: 700;">🪙 ${{c.reward_points || 0}} Pts</span></td>
                        <td style="font-size: 0.80rem; color: #64748B; white-space: nowrap;">${{c.joined || 'Recent'}}</td>
                        <td><span class="badge badge-green" style="font-size: 0.75rem; font-weight: 800;">✓ Active Buyer</span></td>
                    </tr>
                `;
            }}).join('');
        }}

        function filterAdminCustomers() {{
            renderAdminCustomers();
        }}

        async function loadShopCustomersFromBackend() {{
            if (!activeShop) return;
            const code = activeShop.code || activeShop.shop_code;
            try {{
                const res = await fetch(`/api/shop/customers/?shop_code=${{encodeURIComponent(code)}}`);
                const data = await res.json();
                if (data.success && Array.isArray(data.customers)) {{
                    data.customers.forEach(bc => {{
                        const idx = customersData.findIndex(c => c.phone === bc.phone || c.customer_code === bc.customer_code);
                        if (idx >= 0) {{
                            customersData[idx] = {{ ...customersData[idx], ...bc }};
                        }} else {{
                            customersData.unshift(bc);
                        }}
                    }});
                    renderAdminCustomers();
                }}
            }} catch (err) {{
                console.warn('Could not refresh backend customers:', err);
                renderAdminCustomers();
            }}
        }}

        function renderAdminSales() {{
            const tbody = document.getElementById('ownerRecentSalesTbody');
            const emptyEl = document.getElementById('adminReportsEmptyState');
            const wrapperEl = document.getElementById('adminReportsTableWrapper');
            const activeCode = (activeShop && activeShop.code) ? activeShop.code : 'SB-SHOP-001';
            const filteredSales = recentSalesData.filter(s => s.shop_code === activeCode);

            if (filteredSales.length === 0) {{
                if (emptyEl) emptyEl.style.display = 'block';
                if (wrapperEl) wrapperEl.style.display = 'none';
                if (tbody) tbody.innerHTML = '';
                return;
            }}

            if (emptyEl) emptyEl.style.display = 'none';
            if (wrapperEl) wrapperEl.style.display = 'block';
            if (!tbody) return;
            tbody.innerHTML = '';

            filteredSales.forEach(s => {{
                tbody.innerHTML += `
                    <tr>
                        <td>
                            <code style="font-weight: 800; color: #0F5132; background: #DCFCE7; padding: 4px 8px; border-radius: 6px; font-size: 0.82rem; font-family: monospace;">${{s.bill_number}}</code>
                        </td>
                        <td>
                            <strong style="color: #0F172A;">${{s.customer_name}}</strong>
                            <div style="font-size: 0.75rem; color: #64748B;">${{s.customer_phone}}</div>
                        </td>
                        <td>
                            <span style="font-weight: 600; color: #1E293B;">${{s.cashier_name}}</span>
                            <div style="font-size: 0.72rem; color: #64748B;">ID: ${{s.cashier_id}}</div>
                        </td>
                        <td style="color: var(--success); font-weight: 800; font-size: 0.95rem;">
                            ₹${{parseFloat(s.final_total).toFixed(2)}}
                        </td>
                        <td>
                            <span class="badge badge-purple" style="font-size: 0.75rem;">${{s.payment_method}}</span>
                        </td>
                        <td style="font-size: 0.82rem; color: #475569;">
                            ${{s.created_at}}
                        </td>
                    </tr>
                `;
            }});
        }}

        let activeWorkerVerificationId = null;

        async function sendWorkerOtp() {{
            // Strict pre-validation: only go for send otp if all things are correct!
            const isValid = validateWorkerForm(true);
            if (!isValid) {{
                return; // STOP! Gated until phone is exact 10 digits and password is strong & double verified
            }}

            const name = document.getElementById('newWorkerName').value.trim();
            const phone = document.getElementById('newWorkerPhone').value.trim();
            const email = document.getElementById('newWorkerEmail').value.trim();
            const workerId = document.getElementById('newWorkerId').value.trim();
            const employeeCode = document.getElementById('newEmployeeCode') ? document.getElementById('newEmployeeCode').value.trim() : '';
            const role = document.getElementById('newWorkerRole') ? document.getElementById('newWorkerRole').value : 'CASHIER';
            const password = document.getElementById('newWorkerPassword').value;
            const msgEl = document.getElementById('workerMsg');
            const btn = document.getElementById('btnSendWorkerOtp');

            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = '<span>⏳ Sending Verification OTP to Gmail...</span>';
            }}

            try {{
                const res = await fetch('/api/admin/workers/send-otp/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ 
                        full_name: name,
                        name: name,
                        worker_name: name,
                        phone_number: phone, 
                        phone: phone,
                        email: email,
                        username: workerId,
                        worker_id: workerId,
                        employee_id: employeeCode,
                        role_in_shop: role,
                        password: password,
                        shop_code: (typeof activeShop !== 'undefined' && activeShop?.code) ? activeShop.code : ''
                    }})
                }});
                let data = null;
                try {{
                    data = await res.json();
                }} catch (parseErr) {{
                    throw new Error('Server returned non-JSON response (HTTP ' + res.status + ')');
                }}
                if (data && data.success) {{
                    activeWorkerVerificationId = data.verification_id;
                    document.getElementById('workerOtpStep1').style.display = 'none';
                    document.getElementById('workerOtpStep2').style.display = 'block';
                    msgEl.style.display = 'block';
                    msgEl.style.background = '#DCFCE7';
                    msgEl.style.color = '#15803D';
                    msgEl.style.border = '1.5px solid #86EFAC';
                    msgEl.innerHTML = `✓ 6-Digit OTP dispatched to <strong>${{email}}</strong>.<br>Enter OTP below to authorize worker <strong>${{name}}</strong> (Phone: ${{phone}}, ID: <code>${{workerId}}</code>).`;
                }} else {{
                    alert('Failed to send OTP: ' + (data.error || 'Server error.'));
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '<span>📧 Send Verification OTP to Worker Gmail</span>';
                }}
            }}
        }}

        async function verifyAndAddWorker() {{
            const isValid = validateWorkerForm(true);
            if (!isValid) return;

            const name = document.getElementById('newWorkerName').value.trim();
            const phone = document.getElementById('newWorkerPhone').value.trim();
            const email = document.getElementById('newWorkerEmail').value.trim();
            const role = document.getElementById('newWorkerRole').value;
            const workerId = document.getElementById('newWorkerId').value.trim();
            const employeeCode = document.getElementById('newEmployeeCode') ? document.getElementById('newEmployeeCode').value.trim() : '';
            const password = document.getElementById('newWorkerPassword').value;
            const otp = document.getElementById('workerOtpInput').value.trim();
            const msgEl = document.getElementById('workerMsg');

            if (!otp || otp.length < 6) {{
                alert('Please enter the 6-digit OTP received on worker Gmail.');
                return;
            }}

            try {{
                const res = await fetch('/api/admin/workers/create/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ 
                        verification_id: activeWorkerVerificationId,
                        full_name: name, 
                        name: name,
                        worker_name: name,
                        phone_number: phone, 
                        phone: phone,
                        email: email, 
                        role_in_shop: role, 
                        otp: otp,
                        username: workerId,
                        worker_id: workerId,
                        employee_id: employeeCode,
                        password: password,
                        shop_code: (typeof activeShop !== 'undefined' && activeShop?.code) ? activeShop.code : ''
                    }})
                }});
                let data = null;
                try {{
                    data = await res.json();
                }} catch (parseErr) {{
                    throw new Error('Server returned non-JSON response (HTTP ' + res.status + ')');
                }}
                if (data && data.success) {{
                    const wId = (data.worker && data.worker.worker_id) || data.username || workerId;
                    const wPass = (data.worker && data.worker.password) || password;
                    const wName = (data.worker && data.worker.name) || data.name || name;

                    msgEl.style.display = 'block';
                    msgEl.style.background = '#DCFCE7';
                    msgEl.style.color = '#15803D';
                    msgEl.style.border = '1.5px solid #86EFAC';
                    msgEl.innerHTML = `
                        <div style="font-weight: 800; font-size: 0.95rem; margin-bottom: 4px;">✓ Worker "${{wName}}" Verified & Created!</div>
                        <div style="font-size: 0.82rem; margin-bottom: 8px;">Worker can now log into the POS terminal with verified credentials:</div>
                        <div style="display: flex; gap: 8px; align-items: center; background: white; padding: 8px 12px; border-radius: 6px; border: 1.5px solid #86EFAC; flex-wrap: wrap;">
                            <span>Unique Login ID: <code style="font-weight: 800; color: #0F5132;">${{wId}}</code></span>
                            <span style="color: #CBD5E1;">|</span>
                            <span>Phone: <strong>${{phone}}</strong></span>
                            <span style="color: #CBD5E1;">|</span>
                            <span>Password: <code style="font-weight: 800; color: #1E293B;">${{wPass}}</code></span>
                            <button onclick="navigator.clipboard.writeText('${{wId}} / ${{wPass}}'); alert('Credentials copied to clipboard!');" class="btn btn-sm btn-outline" style="margin-left: auto; padding: 2px 8px; font-size: 0.72rem;">📋 Copy Credentials</button>
                        </div>
                    `;

                    if (data.worker) {{
                        workersData.unshift(data.worker);
                    }} else {{
                        workersData.unshift({{
                            user_id: data.worker_id || data.employee_id || wId,
                            worker_id: wId,
                            name: wName,
                            phone: phone,
                            email: email,
                            role: role,
                            is_active: true,
                            created_at: 'Just now',
                            password: wPass
                        }});
                    }}
                    renderAdminWorkers();
                    renderQuickAccessWorkers();

                    // Reset form
                    document.getElementById('newWorkerName').value = '';
                    document.getElementById('newWorkerPhone').value = '';
                    document.getElementById('newWorkerEmail').value = '';
                    document.getElementById('newWorkerId').value = '';
                    document.getElementById('newWorkerPassword').value = 'CashierPass@123';
                    if (document.getElementById('newWorkerConfirmPassword')) document.getElementById('newWorkerConfirmPassword').value = '';
                    document.getElementById('workerOtpStep2').style.display = 'none';
                    document.getElementById('workerOtpStep1').style.display = 'block';
                    activeWorkerVerificationId = null;
                }} else {{
                    alert('Verification failed: ' + (data.error || 'Unknown error'));
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        function openWorkerResetPassModal(userId, workerName, workerId) {{
            document.getElementById('resetModalUserId').value = userId;
            document.getElementById('resetModalWorkerName').innerText = workerName;
            document.getElementById('resetModalWorkerId').innerText = workerId;
            document.getElementById('resetModalNewPass').value = 'CashierPass@' + Math.floor(100 + Math.random() * 900);
            document.getElementById('resetModalMsg').style.display = 'none';
            document.getElementById('workerResetPassModal').style.display = 'flex';
        }}

        function closeWorkerResetPassModal() {{
            document.getElementById('workerResetPassModal').style.display = 'none';
        }}

        function generateResetModalPass() {{
            document.getElementById('resetModalNewPass').value = 'Pass@' + Math.floor(1000 + Math.random() * 9000);
        }}

        async function submitWorkerResetPassword() {{
            const userId = document.getElementById('resetModalUserId').value;
            const newPass = document.getElementById('resetModalNewPass').value.trim();
            const msgEl = document.getElementById('resetModalMsg');

            if (!newPass || newPass.length < 4) {{
                alert('Password must be at least 4 characters long.');
                return;
            }}

            try {{
                const res = await fetch('/api/admin/workers/reset-password/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ user_id: userId, new_password: newPass }})
                }});
                const data = await res.json();
                if (data.success) {{
                    msgEl.style.display = 'block';
                    msgEl.style.background = '#DCFCE7';
                    msgEl.style.color = '#15803D';
                    msgEl.innerText = `✓ ${{data.message}} Worker can now log in with the new password.`;
                    const w = workersData.find(item => item.user_id === userId);
                    if (w) {{
                        w.password = newPass;
                    }}
                    setTimeout(() => {{ closeWorkerResetPassModal(); }}, 2000);
                }} else {{
                    alert('Reset failed: ' + data.error);
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        async function toggleWorkerAccess(userId) {{
            try {{
                const res = await fetch('/api/admin/workers/toggle-access/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ user_id: userId }})
                }});
                const data = await res.json();
                if (data.success) {{
                    const w = workersData.find(item => item.user_id === userId);
                    if (w) {{
                        w.is_active = data.is_active;
                    }}
                    renderAdminWorkers();
                }} else {{
                    alert('Action failed: ' + data.error);
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        async function deleteWorker(userId, workerName) {{
            if (!confirm(`Are you sure you want to remove worker "${{workerName}}"? This will revoke their POS billing access.`)) {{
                return;
            }}
            try {{
                const res = await fetch('/api/admin/workers/delete/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: jsonStringifySafe({{ user_id: userId }})
                }});
                const data = await res.json();
                if (data.success) {{
                    workersData = workersData.filter(w => w.user_id !== userId);
                    renderAdminWorkers();
                }} else {{
                    alert('Remove failed: ' + data.error);
                }}
            }} catch (err) {{
                alert('Request failed: ' + err.message);
            }}
        }}

        // Helper safe json stringify
        function jsonStringifySafe(obj) {{
            return JSON.stringify(obj);
        }}

        // ======================= POS BARCODE SCANNER =======================
        function playScanBeep() {{
            try {{
                const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
                const osc = audioCtx.createOscillator();
                const gain = audioCtx.createGain();
                osc.connect(gain);
                gain.connect(audioCtx.destination);
                osc.frequency.value = 1760;
                gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
                osc.start();
                osc.stop(audioCtx.currentTime + 0.12);
            }} catch(e) {{}}
        }}

        function showBarcodeFeedback(bg, color, htmlMsg) {{
            const banner = document.getElementById('barcodeFeedbackBanner');
            if (!banner) return;
            banner.style.display = 'block';
            banner.style.background = bg;
            banner.style.color = color;
            banner.innerHTML = htmlMsg;
        }}

        async function scanBarcodeFromInput() {{
            const input = document.getElementById('posBarcodeInput');
            if (!input) return;
            const code = input.value.trim();
            if (!code) {{
                showBarcodeFeedback(
                    '#FEF3C7',
                    '#92400E',
                    '⚠️ Type or scan a barcode number in the input box (e.g. <code>8901000000001</code>), click <strong>📤 Upload Barcode Image</strong> to scan from a PNG/JPG file, or pick a quick sample barcode below.'
                );
                input.focus();
                input.style.borderColor = '#F59E0B';
                setTimeout(() => {{ input.style.borderColor = ''; }}, 1500);
                return;
            }}
            await processBarcodeScan(code);
            input.value = '';
            input.focus();
        }}

        function simulateBarcodeScan(code) {{
            const input = document.getElementById('posBarcodeInput');
            if (input) input.value = code;
            scanBarcodeFromInput();
        }}

        function upsertScannedProduct(prodData, code, stock) {{
            const activeCode = (activeShop && activeShop.code) ? activeShop.code : 'SB-SHOP-001';
            let p = productsData.find(item => String(item.id) === String(prodData.id));
            if (!p) {{
                p = {{
                    id: prodData.id,
                    shop_code: prodData.shop_code || activeCode,
                    shop_id: prodData.shop_id || (activeShop ? activeShop.id : ''),
                    name: prodData.name,
                    barcode: code,
                    selling_price: parseFloat(prodData.selling_price),
                    mrp: parseFloat(prodData.mrp),
                    tax_rate: parseFloat(prodData.tax_rate),
                    stock: stock != null ? parseFloat(stock) : 500,
                    unit: prodData.unit || 'PCS',
                    category: prodData.category_name || 'General'
                }};
                productsData.unshift(p);
            }}
            return p;
        }}

        async function processBarcodeScan(code, previewDataUrl = null) {{
            const cleanCode = String(code).trim().toLowerCase();
            const activeCode = (activeShop && activeShop.code) ? activeShop.code : 'SB-SHOP-001';
            let p = productsData.find(item =>
                (!item.shop_code || item.shop_code === activeCode) &&
                (String(item.barcode).trim().toLowerCase() === cleanCode ||
                 String(item.id).trim().toLowerCase() === cleanCode)
            );

            if (!p) {{
                try {{
                    const res = await fetch(`/api/products/barcode/${{encodeURIComponent(code.trim())}}/?shop_code=${{encodeURIComponent(activeCode)}}`);
                    if (res.ok) {{
                        const data = await res.json();
                        if (data.found && data.product) {{
                            p = upsertScannedProduct(data.product, code.trim(), data.available_stock);
                        }}
                    }}
                }} catch(e) {{
                    console.error('Barcode fetch error', e);
                }}
            }}

            if (p) {{
                addToCart(p.id);
                const imgSrc = previewDataUrl || `/api/products/barcode-image/${{encodeURIComponent(p.barcode)}}/?text=0`;
                showBarcodeFeedback('#DCFCE7', '#15803D', `
                    <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                        <div style="display: flex; align-items: center; gap: 10px;">
                            <img src="${{imgSrc}}" style="height: 34px; max-width: 110px; object-fit: contain; background: white; padding: 2px 6px; border-radius: 4px; border: 1px solid #86EFAC;" alt="Barcode">
                            <div>
                                <div>✓ <strong>BARCODE SCANNED [${{p.barcode}}]:</strong> Automatically added <strong>${{p.name}}</strong> (₹${{p.selling_price.toFixed(2)}}) to Cart!</div>
                                <div style="font-size: 0.78rem; color: #166534;">Category: ${{p.category}} &bull; Available Stock: ${{p.stock}} ${{p.unit}}</div>
                            </div>
                        </div>
                        <button type="button" onclick="document.getElementById('barcodeFeedbackBanner').style.display='none'" style="background: none; border: none; font-size: 1rem; cursor: pointer; color: #15803D;">✕</button>
                    </div>
                `);
                playScanBeep();
            }} else {{
                showBarcodeFeedback('#FEE2E2', '#B91C1C', `✕ <strong>BARCODE NOT FOUND [${{code}}]:</strong> No product matches this barcode in this store.`);
            }}
        }}

        function handleBarcodeImageUpload(event) {{
            const file = event.target && event.target.files && event.target.files[0];
            if (!file) return;
            decodeUploadedImageFile(file);
            event.target.value = '';
        }}

        function handleBarcodeDrop(event) {{
            event.preventDefault();
            const zone = document.getElementById('barcodeScannerDropZone');
            if (zone) zone.style.background = '#DCFCE7';
            const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
            if (file) {{
                decodeUploadedImageFile(file);
            }}
        }}

        async function decodeUploadedImageFile(file) {{
            let previewUrl = null;
            try {{
                previewUrl = URL.createObjectURL(file);
            }} catch(e) {{}}

            showBarcodeFeedback('#DCFCE7', '#0F5132', `⏳ Reading &amp; decoding barcode from uploaded image <strong>${{file.name}}</strong>...`);

            try {{
                const formData = new FormData();
                formData.append('image', file);
                const res = await fetch('/api/products/decode-barcode-image/', {{
                    method: 'POST',
                    body: formData
                }});
                const data = await res.json();

                if (data.success && data.found && data.product) {{
                    const p = upsertScannedProduct(data.product, data.decoded_text, data.available_stock);
                    addToCart(p.id);
                    const imgSrc = previewUrl || `/api/products/barcode-image/${{encodeURIComponent(data.decoded_text)}}/?text=0`;
                    showBarcodeFeedback('#DCFCE7', '#15803D', `
                        <div style="display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 10px;">
                            <div style="display: flex; align-items: center; gap: 10px;">
                                <img src="${{imgSrc}}" style="height: 36px; max-width: 120px; object-fit: contain; background: white; padding: 2px 6px; border-radius: 4px; border: 1px solid #86EFAC;" alt="Uploaded Barcode">
                                <div>
                                    <div>✓ <strong>UPLOADED IMAGE DECODED [${{data.decoded_text}} • ${{data.format}}]:</strong> Added <strong>${{p.name}}</strong> (₹${{p.selling_price.toFixed(2)}}) to Cart!</div>
                                    <div style="font-size: 0.78rem; color: #166534;">Stock: ${{p.stock}} ${{p.unit}}</div>
                                </div>
                            </div>
                            <button type="button" onclick="document.getElementById('barcodeFeedbackBanner').style.display='none'" style="background: none; border: none; font-size: 1rem; cursor: pointer; color: #15803D;">✕</button>
                        </div>
                    `);
                    playScanBeep();
                }} else if (data.success && !data.found) {{
                    showBarcodeFeedback('#FEF3C7', '#92400E', `⚠️ Barcode decoded as <code>${{data.decoded_text}}</code> (${{data.format}}), but no matching product exists in store inventory.`);
                }} else {{
                    showBarcodeFeedback('#FEE2E2', '#B91C1C', `✕ <strong>Image Scan Failed:</strong> ${{data.error || 'Could not detect a valid barcode in this image.'}}`);
                }}
            }} catch (err) {{
                showBarcodeFeedback('#FEE2E2', '#B91C1C', `✕ Upload scan error: ${{err.message}}`);
            }}
        }}

        let webcamStream = null;
        let webcamTimer = null;
        let webcamBusy = false;

        async function openWebcamScannerModal() {{
            const modal = document.getElementById('webcamScannerModal');
            const video = document.getElementById('webcamPreviewVideo');
            const statusEl = document.getElementById('webcamStatusText');
            if (!modal || !video) return;
            modal.style.display = 'flex';
            statusEl.innerText = 'Starting camera... hold a barcode in the frame.';

            try {{
                webcamStream = await navigator.mediaDevices.getUserMedia({{ video: {{ facingMode: 'environment' }} }});
                video.srcObject = webcamStream;
                if (webcamTimer) clearInterval(webcamTimer);
                webcamTimer = setInterval(async () => {{
                    if (webcamBusy || !webcamStream || video.readyState < 2) return;
                    webcamBusy = true;
                    try {{
                        const canvas = document.getElementById('webcamCaptureCanvas');
                        canvas.width = video.videoWidth || 640;
                        canvas.height = video.videoHeight || 480;
                        const ctx = canvas.getContext('2d');
                        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
                        const dataUrl = canvas.toDataURL('image/jpeg', 0.8);
                        const res = await fetch('/api/products/decode-barcode-image/', {{
                            method: 'POST',
                            headers: {{ 'Content-Type': 'application/json' }},
                            body: JSON.stringify({{ image_base64: dataUrl }})
                        }});
                        const data = await res.json();
                        if (data.success && data.found && data.product) {{
                            const p = upsertScannedProduct(data.product, data.decoded_text, data.available_stock);
                            addToCart(p.id);
                            playScanBeep();
                            showBarcodeFeedback('#DCFCE7', '#15803D', `✓ <strong>CAMERA SCANNED [${{data.decoded_text}}]:</strong> Added <strong>${{p.name}}</strong> (₹${{p.selling_price.toFixed(2)}}) to Cart!`);
                            closeWebcamScannerModal();
                        }}
                    }} catch (_) {{}} finally {{
                        webcamBusy = false;
                    }}
                }}, 650);
            }} catch (err) {{
                statusEl.innerHTML = `<span style="color: var(--danger);">Camera unavailable (${{err.message}}). Use <strong>Upload Barcode Image</strong> below to test!</span>`;
            }}
        }}

        function closeWebcamScannerModal() {{
            if (webcamTimer) {{ clearInterval(webcamTimer); webcamTimer = null; }}
            if (webcamStream) {{
                webcamStream.getTracks().forEach(t => t.stop());
                webcamStream = null;
            }}
            const modal = document.getElementById('webcamScannerModal');
            if (modal) modal.style.display = 'none';
        }}

        // ======================= POS TERMINAL =======================
        let activePosPhone = '';

        function setPosUnlocked(unlocked) {{
            const posSec = document.getElementById('posBillingSection');
            const lockOverlay = document.getElementById('posLockOverlay');
            if (unlocked) {{
                if (lockOverlay) lockOverlay.style.display = 'none';
                if (posSec) {{
                    posSec.style.opacity = '1';
                    posSec.style.filter = 'none';
                }}
            }} else {{
                if (lockOverlay) lockOverlay.style.display = 'flex';
                if (posSec) {{
                    posSec.style.opacity = '0.45';
                    posSec.style.filter = 'none';
                }}
            }}
        }}

        function focusCustomerPhoneStep1() {{
            const card = document.getElementById('posCustomerGateCard');
            if (card) {{
                card.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
                card.style.boxShadow = '0 0 0 4px rgba(15, 81, 50, 0.35)';
                setTimeout(() => {{ card.style.boxShadow = '0 4px 15px rgba(15, 81, 50, 0.08)'; }}, 1200);
            }}
            const phoneInput = document.getElementById('posCustPhoneInput');
            if (phoneInput) phoneInput.focus();
        }}

        function promptStep1First() {{
            focusCustomerPhoneStep1();
        }}

        function resetCustomerLookup() {{
            attachedCustomer = null;
            const stepAttached = document.getElementById('posCustAttachedStep');
            const stepRegister = document.getElementById('posCustRegisterStep');
            const stepSearch = document.getElementById('posCustSearchStep');

            if (stepAttached) stepAttached.style.display = 'none';
            if (stepRegister) stepRegister.style.display = 'none';
            if (stepSearch) stepSearch.style.display = 'block';

            const badge = document.getElementById('posStatusBadgeText');
            if (badge) {{
                badge.className = 'badge badge-amber';
                badge.innerText = '⏳ Step 1: Customer Mobile No. Required';
            }}

            const phoneInput = document.getElementById('posCustPhoneInput');
            if (phoneInput) {{
                phoneInput.value = '';
                setTimeout(() => phoneInput.focus(), 250);
            }}

            const searchErr = document.getElementById('custSearchError');
            if (searchErr) searchErr.style.display = 'none';

            setPosUnlocked(false);
        }}

        function testCustSearch(phone) {{
            const input = document.getElementById('posCustPhoneInput');
            if (input) input.value = phone;
            searchCustomerPos();
        }}

        async function searchCustomerPos() {{
            const phoneInput = document.getElementById('posCustPhoneInput');
            const phone = phoneInput.value.trim();
            const errEl = document.getElementById('custSearchError');
            if (errEl) errEl.style.display = 'none';

            if (!phone || phone.length < 10) {{
                if (errEl) {{
                    errEl.innerText = 'Please enter a valid 10-digit customer mobile number.';
                    errEl.style.display = 'block';
                }} else {{
                    alert('Please enter a valid 10-digit customer mobile number.');
                }}
                return;
            }}

            activePosPhone = phone;

            // 1. Check local memory first for instant hit
            const localCust = (customersData || []).find(c => c.phone === phone);
            if (localCust) {{
                attachCustomerToPos(localCust);
                return;
            }}

            try {{
                const res = await fetch(`/api/auth/customers/search/?phone=${{encodeURIComponent(phone)}}`);
                const data = await res.json();

                if (data.exists && data.customer) {{
                    // Customer already exists in database -> Proceed directly to billing!
                    const cust = data.customer;
                    const shopCode = (activeShop ? activeShop.code : '') || 'SB-SHOP-001';
                    const shopName = (activeShop ? activeShop.name : '') || 'Store';

                    // Ensure customer is reflected in customersData under this store
                    const existingIdx = customersData.findIndex(c => c.phone === (cust.phone_number || phone));
                    const custItem = {{
                        id: cust.id,
                        customer_code: cust.customer_code || 'SB-CUST',
                        name: cust.full_name || cust.name || 'Customer',
                        phone: cust.phone_number || phone,
                        email: cust.email || '',
                        shop_code: cust.shop_code || shopCode,
                        shop_name: cust.shop_name || shopName,
                        registered_by: cust.registered_by || currentCashierName || 'Cashier / POS Staff',
                        registered_by_id: currentCashierId || '',
                        total_spent: parseFloat(cust.total_spent) || 0.0,
                        visit_count: (cust.visit_count || 0) + 1,
                        reward_points: cust.reward_points || 0,
                        joined: 'Verified Member',
                        is_verified: true
                    }};
                    if (existingIdx >= 0) {{
                        customersData[existingIdx] = {{ ...customersData[existingIdx], ...custItem }};
                    }} else {{
                        customersData.unshift(custItem);
                    }}
                    if (typeof renderAdminCustomers === 'function') renderAdminCustomers();

                    attachCustomerToPos(cust);
                }} else {{
                    // Customer not found -> Cashier must 1st add customer then proceed!
                    openPosRegistration(phone);
                }}
            }} catch (err) {{
                console.warn('Network search error, using registration fallback:', err);
                openPosRegistration(phone);
            }}
        }}

        function openPosRegistration(phone) {{
            document.getElementById('posCustSearchStep').style.display = 'none';
            document.getElementById('posCustRegisterStep').style.display = 'block';
            document.getElementById('posCustAttachedStep').style.display = 'none';

            document.getElementById('regCustPhone').value = phone;
            document.getElementById('regStep1').style.display = 'block';
            document.getElementById('regStep2').style.display = 'none';
            document.getElementById('regCustName').value = '';
            document.getElementById('regCustEmail').value = '';

            const banner = document.getElementById('regNotFoundBanner');
            if (banner) {{
                banner.innerHTML = `
                    <div style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px;">
                        <div>
                            <strong style="color: #92400E; font-size: 0.98rem;">⚠️ Mobile Number (${{phone}}) Not Registered in Database</strong>
                            <div style="color: #B45309; font-size: 0.84rem; margin-top: 2px;">Cashier must first add &amp; verify this customer via 6-digit Gmail OTP to unlock billing.</div>
                        </div>
                        <button type="button" onclick="resetCustomerLookup()" class="btn btn-sm btn-outline" style="padding: 4px 12px; font-size: 0.78rem; border-color: #F59E0B; color: #92400E; font-weight: 700;">
                            &larr; Try Another Mobile No.
                        </button>
                    </div>
                `;
            }}

            const badge = document.getElementById('posStatusBadgeText');
            if (badge) {{
                badge.className = 'badge badge-purple';
                badge.innerText = '📝 Registering New Customer';
            }}

            setTimeout(() => {{
                const nameInput = document.getElementById('regCustName');
                if (nameInput) nameInput.focus();
            }}, 200);
        }}

        let activePosCustomerVerificationId = null;

        async function sendCustomerRegOtp() {{
            const name = document.getElementById('regCustName').value.trim();
            const phone = document.getElementById('regCustPhone').value.trim();
            const email = document.getElementById('regCustEmail').value.trim();
            const consent = document.getElementById('regCustConsent').checked;

            if (!name) {{ alert('Please enter Customer Full Name.'); return; }}
            if (!phone || phone.length < 10) {{ alert('Please enter a valid 10-digit Mobile Number.'); return; }}
            if (!email || !email.includes('@')) {{ alert('Please enter a valid Customer Gmail address.'); return; }}
            if (!consent) {{ alert('Customer consent is required to complete registration.'); return; }}

            const btn = document.getElementById('btnSendCustRegOtp');
            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = '<span>⏳ Sending OTP via Gmail API...</span>';
            }}

            try {{
                const res = await fetch('/api/shop/customers/send-otp', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        full_name: name,
                        phone_number: phone,
                        email: email,
                        shop_id: (activeShop ? activeShop.code || activeShop.id : null) || (typeof currentShopId !== 'undefined' ? currentShopId : null)
                    }})
                }});
                const data = await res.json();
                if (data.success) {{
                    activePosCustomerVerificationId = data.verification_id;
                    document.getElementById('regStep1').style.display = 'none';
                    document.getElementById('regStep2').style.display = 'block';
                    document.getElementById('regOtpMsg').innerHTML = `
                        ✓ 6-Digit OTP dispatched to <strong>${{email}}</strong> via official Gmail API.<br>
                        <span style="color: var(--text-muted); font-size: 0.8rem;">Enter the code below to complete registration and activate customer profile.</span>
                    `;
                    document.getElementById('regCustOtp').value = '';
                    document.getElementById('regCustOtp').focus();
                }} else {{
                    alert('Registration failed: ' + (data.error || 'Unable to dispatch Gmail API message.'));
                    if (btn) {{
                        btn.disabled = false;
                        btn.innerHTML = '<span>✉️ Send Customer Verification OTP</span>';
                    }}
                }}
            }} catch (e) {{
                alert('Request failed: ' + e.message);
                if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '<span>✉️ Send Customer Verification OTP</span>';
                }}
            }}
        }}

        async function verifyCustomerRegOtp() {{
            const name = document.getElementById('regCustName').value.trim();
            const phone = document.getElementById('regCustPhone').value.trim();
            const email = document.getElementById('regCustEmail').value.trim();
            const otp = document.getElementById('regCustOtp').value.trim();

            if (!otp || otp.length < 6) {{ alert('Please enter the 6-digit verification code.'); return; }}

            const btn = document.getElementById('btnVerifyCustRegOtp');
            if (btn) {{
                btn.disabled = true;
                btn.innerHTML = '⏳ Verifying & Registering Customer...';
            }}

            try {{
                const shopIdToSend = (activeShop ? (activeShop.code || activeShop.id) : null) || (typeof currentShopId !== 'undefined' ? currentShopId : null);
                const cashierUserToSend = (typeof currentCashierId !== 'undefined' && currentCashierId) ? currentCashierId : (typeof currentCashierName !== 'undefined' ? currentCashierName : 'cashier_arun');

                const res = await fetch('/api/shop/customers/create/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        verification_id: activePosCustomerVerificationId,
                        email: email,
                        otp: otp,
                        full_name: name,
                        phone_number: phone,
                        shop_id: shopIdToSend,
                        worker_id: cashierUserToSend,
                        worker_username: cashierUserToSend
                    }})
                }});
                let data = null;
                const rawText = await res.text();
                try {{
                    data = JSON.parse(rawText);
                }} catch (parseErr) {{
                    const match = rawText.match(/<title>(.*?)<\/title>/i) || rawText.match(/<h1[^>]*>(.*?)<\/h1>/i);
                    const errorDetail = match ? match[1] : ('HTTP ' + res.status);
                    alert('Server error (' + res.status + '): ' + errorDetail);
                    return;
                }}
                if (data && data.success && data.customer) {{
                    const newCust = data.customer;
                    const shopCode = (activeShop ? activeShop.code : '') || 'SB-SHOP-001';
                    const shopName = (activeShop ? activeShop.name : '') || 'Store';
                    const workerLabel = (typeof currentCashierName !== 'undefined' && currentCashierName) ? `${{currentCashierName}} (${{currentCashierId || 'Worker'}})` : 'Cashier / POS Staff';

                    // Combine newly added customer into customersData for the store owner
                    const newCustRecord = {{
                        id: newCust.id,
                        customer_code: newCust.customer_code || 'SB-CUST',
                        name: newCust.name || name,
                        phone: newCust.phone || phone,
                        email: newCust.email || email,
                        shop_id: newCust.shop_id || (activeShop ? activeShop.id : ''),
                        shop_code: newCust.shop_code || shopCode,
                        shop_name: newCust.shop_name || shopName,
                        registered_by: newCust.registered_by || workerLabel,
                        registered_by_id: cashierUserToSend,
                        total_spent: 0.0,
                        visit_count: 1,
                        reward_points: 0,
                        joined: 'Just Now',
                        is_verified: true
                    }};

                    const existIdx = customersData.findIndex(c => c.phone === phone || c.customer_code === newCustRecord.customer_code);
                    if (existIdx >= 0) {{
                        customersData[existIdx] = {{ ...customersData[existIdx], ...newCustRecord }};
                    }} else {{
                        customersData.unshift(newCustRecord);
                    }}

                    // Update Store Owner KPI & Customer table
                    if (typeof renderAdminCustomers === 'function') {{
                        renderAdminCustomers();
                    }}

                    attachCustomerToPos(newCust);
                    alert(`✓ Customer "${{name}}" successfully verified via Gmail OTP and registered to ${{shopName}}!\nBilling terminal unlocked.`);
                }} else {{
                    alert('Verification error: ' + (data.error || 'Invalid OTP code.'));
                }}
            }} catch (e) {{
                alert('Error: ' + e.message);
            }} finally {{
                if (btn) {{
                    btn.disabled = false;
                    btn.innerHTML = '✓ Verify OTP & Attach to Bill';
                }}
            }}
        }}

        function closeCustomerRegModal() {{
            const regStep = document.getElementById('posCustRegisterStep');
            if (regStep) regStep.style.display = 'none';
        }}

        function attachCustomerToPos(cust) {{
            attachedCustomer = {{
                id: cust.id,
                name: cust.full_name || cust.name || 'Customer',
                phone: cust.phone_number || cust.phone || cust.masked_phone || activePosPhone || 'N/A',
                email: cust.email || cust.masked_email || 'N/A',
                code: cust.customer_code || 'SB-CUST',
                points: cust.reward_points != null ? cust.reward_points : 0,
                registered_by: cust.registered_by || ''
            }};

            document.getElementById('posCustSearchStep').style.display = 'none';
            document.getElementById('posCustRegisterStep').style.display = 'none';
            document.getElementById('posCustAttachedStep').style.display = 'block';

            document.getElementById('attachedCustName').innerText = attachedCustomer.name;
            document.getElementById('attachedCustPhone').innerText = attachedCustomer.phone;
            document.getElementById('attachedCustEmail').innerText = attachedCustomer.email;
            document.getElementById('attachedCustCode').innerText = attachedCustomer.code;
            document.getElementById('attachedCustPts').innerText = attachedCustomer.points + ' Pts';

            const regWorkerEl = document.getElementById('attachedCustWorkerInfo');
            if (regWorkerEl) {{
                regWorkerEl.innerText = attachedCustomer.registered_by ? `(Added by: ${{attachedCustomer.registered_by}})` : '';
            }}

            const badge = document.getElementById('posStatusBadgeText');
            if (badge) {{
                badge.className = 'badge badge-green';
                badge.innerText = '✓ Ready to Scan & Bill';
            }}

            // Unlock POS billing station
            setPosUnlocked(true);

            // Auto-focus barcode scanner
            setTimeout(() => {{
                const bInput = document.getElementById('posBarcodeInput');
                if (bInput) bInput.focus();
            }}, 250);
        }}

        function continueAsGuest() {{
            attachedCustomer = {{
                id: null,
                name: 'Walk-in Guest',
                phone: 'N/A',
                email: 'N/A',
                code: 'WALK-IN',
                points: 0
            }};

            document.getElementById('posCustSearchStep').style.display = 'none';
            document.getElementById('posCustRegisterStep').style.display = 'none';
            document.getElementById('posCustAttachedStep').style.display = 'block';

            document.getElementById('attachedCustName').innerText = 'Walk-in Guest';
            document.getElementById('attachedCustPhone').innerText = 'N/A (Unregistered)';
            document.getElementById('attachedCustEmail').innerText = 'N/A';
            document.getElementById('attachedCustCode').innerText = 'WALK-IN';
            document.getElementById('attachedCustPts').innerText = '0 Pts';

            const badge = document.getElementById('posStatusBadgeText');
            if (badge) {{
                badge.className = 'badge badge-green';
                badge.innerText = '✓ Walk-in Guest Active';
            }}

            // Unlock POS billing station
            setPosUnlocked(true);

            // Auto-focus barcode scanner
            setTimeout(() => {{
                const bInput = document.getElementById('posBarcodeInput');
                if (bInput) bInput.focus();
            }}, 250);
        }}

        function initPos() {{
            renderCart();
            resetCustomerLookup();
            renderLowStockNotifications(false);
            syncLowStockAlertsFromServer(false);
            // Automatically focus barcode scanner so cashier can scan immediately without clicking
            const inp = document.getElementById('posBarcodeInput');
            if (inp) {{
                setTimeout(() => inp.focus(), 100);
            }}
        }}

        function filterPosCatalog() {{}}
        function renderPosGrid(filteredList = null) {{}}

        function clearCart() {{
            if (cart.length > 0 && !confirm('Are you sure you want to clear all scanned items from this bill?')) {{
                return;
            }}
            cart = [];
            renderCart();
            const inp = document.getElementById('posBarcodeInput');
            if (inp) inp.focus();
        }}

        function addToCart(productId) {{
            const p = productsData.find(item => String(item.id) === String(productId));
            if (!p) return;
            const existing = cart.find(item => String(item.id) === String(productId));
            if (existing) {{
                existing.qty += 1;
            }} else {{
                cart.push({{
                    id: p.id,
                    name: p.name,
                    barcode: p.barcode,
                    price: p.selling_price,
                    tax_rate: p.tax_rate,
                    qty: 1
                }});
            }}
            renderCart();
            // Automatically keep barcode input focused for rapid multi-item scanning
            const inp = document.getElementById('posBarcodeInput');
            if (inp) inp.focus();
        }}

        function removeFromCart(productId) {{
            cart = cart.filter(item => String(item.id) !== String(productId));
            renderCart();
            const inp = document.getElementById('posBarcodeInput');
            if (inp) inp.focus();
        }}

        function updateCartQty(productId, delta) {{
            const item = cart.find(i => String(i.id) === String(productId));
            if (item) {{
                item.qty += delta;
                if (item.qty <= 0) {{
                    removeFromCart(productId);
                    return;
                }}
            }}
            renderCart();
            const inp = document.getElementById('posBarcodeInput');
            if (inp) inp.focus();
        }}

        function renderCart() {{
            const tbody = document.getElementById('cartTbody');
            const mobFloat = document.getElementById('mobileCartFloatBar');
            const totalQty = cart.reduce((sum, item) => sum + item.qty, 0);

            const countBadge = document.getElementById('cartCountBadge');
            const summaryBadge = document.getElementById('cartItemCountSummaryBadge');
            if (countBadge) countBadge.innerText = totalQty;
            if (summaryBadge) summaryBadge.innerText = totalQty + (totalQty === 1 ? ' Item' : ' Items');

            if (cart.length === 0) {{
                tbody.innerHTML = `
                    <tr>
                        <td colspan="5" style="text-align: center; color: var(--text-muted); padding: 42px 14px;">
                            <div style="font-size: 2.4rem; margin-bottom: 8px;">📷</div>
                            <strong style="font-size: 1.05rem; color: #1E293B; display: block; margin-bottom: 4px;">Ready to Scan Barcodes</strong>
                            <span style="font-size: 0.85rem;">Scan any product barcode above or use handheld scanner to automatically add products to this bill.</span>
                        </td>
                    </tr>
                `;
                document.getElementById('cartSubtotal').innerText = '₹0.00';
                document.getElementById('cartTax').innerText = '₹0.00';
                document.getElementById('cartFinalTotal').innerText = '₹0.00';
                if (mobFloat) mobFloat.style.display = 'none';
                return;
            }}

            tbody.innerHTML = '';
            let subtotal = 0;
            let tax = 0;

            cart.forEach(item => {{
                const total = item.price * item.qty;
                const itemTax = total * (item.tax_rate / 100);
                subtotal += total;
                tax += itemTax;

                tbody.innerHTML += `
                    <tr>
                        <td style="padding: 10px 12px;">
                            <strong style="color: #0F172A; font-size: 0.94rem;">${{item.name}}</strong>
                            <div style="font-family: monospace; font-size: 0.75rem; color: #64748B; margin-top: 2px;">🏷️ Barcode: ${{item.barcode || 'N/A'}}</div>
                        </td>
                        <td style="padding: 10px 12px; text-align: right; color: #475569; font-weight: 600;">₹${{item.price.toFixed(2)}}</td>
                        <td style="padding: 10px 12px; text-align: center;">
                            <div style="display: inline-flex; align-items: center; background: #DCFCE7; border-radius: 6px; padding: 2px;">
                                <button type="button" onclick="updateCartQty('${{item.id}}', -1)" style="padding: 2px 8px; border: none; background: none; font-weight: 800; color: var(--primary); cursor: pointer;" title="Decrease Qty">&minus;</button>
                                <span style="margin: 0 4px; font-weight: 700; min-width: 18px; text-align: center;">${{item.qty}}</span>
                                <button type="button" onclick="updateCartQty('${{item.id}}', 1)" style="padding: 2px 8px; border: none; background: none; font-weight: 800; color: var(--primary); cursor: pointer;" title="Increase Qty">+</button>
                            </div>
                        </td>
                        <td style="padding: 10px 12px; text-align: right;"><strong style="color: var(--primary); font-size: 0.95rem;">₹${{total.toFixed(2)}}</strong></td>
                        <td style="padding: 10px 12px; text-align: center;"><button type="button" onclick="removeFromCart('${{item.id}}')" style="border:none; background:none; color:var(--danger); font-size: 1.1rem; cursor:pointer;" title="Remove from Bill">🗑️</button></td>
                    </tr>
                `;
            }});

            const finalTotal = subtotal + tax;
            document.getElementById('cartSubtotal').innerText = '₹' + subtotal.toFixed(2);
            document.getElementById('cartTax').innerText = '₹' + tax.toFixed(2);
            document.getElementById('cartFinalTotal').innerText = '₹' + finalTotal.toFixed(2);

            if (mobFloat) {{
                mobFloat.style.display = 'flex';
                const countEl = document.getElementById('mobCartCountText');
                const totalEl = document.getElementById('mobCartTotalText');
                if (countEl) countEl.innerText = `${{totalQty}} Items`;
                if (totalEl) totalEl.innerText = `₹${{finalTotal.toFixed(2)}} Total`;
            }}
            if (typeof renderDrawerCartItems === 'function') {{
                renderDrawerCartItems();
            }}
            if (typeof renderMobileBottomNav === 'function' && currentRole === 'WORKER') {{
                renderMobileBottomNav('WORKER', 'pos');
            }}
        }}

        function scrollToCart() {{
            const el = document.getElementById('posCartSection');
            if (el) {{
                el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }}
        }}

        // ======================= CASHIER POS: PAYMENT MODE & RAZORPAY ONLINE QR FLOW =======================
        let currentPosPaymentMode = 'CASH';
        let activeRazorpayPollInterval = null;
        let currentRazorpayPlinkId = null;
        let currentRazorpayTxnId = null;

        function setPosPaymentMode(mode) {{
            currentPosPaymentMode = mode;
            const btnCash = document.getElementById('payModeBtnCash');
            const btnOnline = document.getElementById('payModeBtnOnline');
            const badge = document.getElementById('paymentModeBadge');
            const mainBtnLabel = document.getElementById('posMainCheckoutBtnLabel');

            if (mode === 'ONLINE') {{
                if (btnOnline) {{
                    btnOnline.style.border = '2px solid #7C3AED';
                    btnOnline.style.background = '#F5F3FF';
                    btnOnline.style.color = '#6D28D9';
                    btnOnline.style.boxShadow = '0 2px 8px rgba(124, 58, 237, 0.18)';
                }}
                if (btnCash) {{
                    btnCash.style.border = '1.5px solid #CBD5E1';
                    btnCash.style.background = '#FFFFFF';
                    btnCash.style.color = '#475569';
                    btnCash.style.boxShadow = 'none';
                }}
                if (badge) {{
                    badge.className = 'badge badge-purple';
                    badge.innerText = 'Online QR Selected';
                }}
                if (mainBtnLabel) {{
                    mainBtnLabel.innerHTML = '⚡ Generate Razorpay QR &amp; Pay';
                }}
            }} else {{
                if (btnCash) {{
                    btnCash.style.border = '2px solid #16A34A';
                    btnCash.style.background = '#DCFCE7';
                    btnCash.style.color = '#15803D';
                    btnCash.style.boxShadow = '0 2px 6px rgba(22, 163, 74, 0.15)';
                }}
                if (btnOnline) {{
                    btnOnline.style.border = '1.5px solid #CBD5E1';
                    btnOnline.style.background = '#FFFFFF';
                    btnOnline.style.color = '#475569';
                    btnOnline.style.boxShadow = 'none';
                }}
                if (badge) {{
                    badge.className = 'badge badge-green';
                    badge.innerText = 'Cash Selected';
                }}
                if (mainBtnLabel) {{
                    mainBtnLabel.innerHTML = '💵 Complete Cash Checkout &amp; Print Bill';
                }}
            }}
        }}

        function handlePosCheckoutAction() {{
            if (cart.length === 0) {{
                alert('Please add at least one product to the cart before checkout.');
                return;
            }}
            if (currentPosPaymentMode === 'ONLINE') {{
                openRazorpayPaymentModal();
            }} else {{
                checkoutSale('CASH');
            }}
        }}

        async function openRazorpayPaymentModal() {{
            if (cart.length === 0) {{
                alert('Cart is empty.');
                return;
            }}

            let subtotal = 0;
            let tax = 0;
            cart.forEach(item => {{
                const itemTotal = item.price * item.qty;
                subtotal += itemTotal;
                tax += itemTotal * (item.tax_rate / 100);
            }});
            const finalTotal = subtotal + tax;

            const custName = attachedCustomer ? attachedCustomer.name : 'Walk-in Guest';
            const custPhone = attachedCustomer ? attachedCustomer.phone : '';
            const custEmail = attachedCustomer ? attachedCustomer.email : '';
            const curShopCode = (activeShop && activeShop.code) ? activeShop.code : 'SB-SHOP-001';

            document.getElementById('rzpModalAmountText').innerText = '₹' + finalTotal.toFixed(2);
            document.getElementById('rzpModalCustomerText').innerText = 'Customer: ' + custName + ' (' + (custPhone || 'Walk-in') + ')';
            document.getElementById('rzpStatusText').innerHTML = `
                <span style="font-size:1.1rem;">⏳</span>
                <span>Generating dynamic payment QR code via Razorpay...</span>
            `;
            document.getElementById('rzpSuccessActions').style.display = 'none';
            document.getElementById('rzpQrCardContainer').style.opacity = '0.5';

            const modal = document.getElementById('razorpayPaymentModal');
            modal.style.display = 'flex';

            try {{
                const res = await fetch('/api/pos/create-payment-order/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        amount: finalTotal,
                        shop_code: curShopCode,
                        customer_id: attachedCustomer ? attachedCustomer.id : null,
                        customer_name: custName,
                        customer_email: custEmail,
                        customer_phone: custPhone
                    }})
                }});
                const data = await res.json();
                if (data.success && data.qr_image_url) {{
                    currentRazorpayPlinkId = data.plink_id;
                    document.getElementById('rzpQrImage').src = data.qr_image_url;
                    document.getElementById('rzpQrCardContainer').style.opacity = '1';
                    const linkEl = document.getElementById('rzpDirectPayLink');
                    if (linkEl && data.short_url) {{
                        linkEl.href = data.short_url;
                    }}
                    document.getElementById('rzpLiveStatusBox').style.background = '#FFFBEB';
                    document.getElementById('rzpLiveStatusBox').style.borderColor = '#FDE68A';
                    document.getElementById('rzpStatusText').innerHTML = `
                        <span style="font-size:1.1rem;">⏳</span>
                        <span>Waiting for customer to scan &amp; complete payment on phone...</span>
                    `;
                    startRazorpayStatusPolling(data.plink_id);
                }} else {{
                    alert('Error creating Razorpay order: ' + (data.error || 'Unknown error'));
                    closeRazorpayModal();
                }}
            }} catch (err) {{
                alert('Network error initializing payment: ' + err.message);
                closeRazorpayModal();
            }}
        }}

        function startRazorpayStatusPolling(plinkId) {{
            if (activeRazorpayPollInterval) {{
                clearInterval(activeRazorpayPollInterval);
            }}

            activeRazorpayPollInterval = setInterval(async () => {{
                if (!currentRazorpayPlinkId) return;
                try {{
                    const res = await fetch('/api/pos/check-payment-status/?plink_id=' + encodeURIComponent(plinkId));
                    const data = await res.json();
                    if (data.success && data.is_paid) {{
                        onRazorpayPaymentSuccess(data);
                    }}
                }} catch (e) {{
                    console.warn('Polling error:', e);
                }}
            }}, 2000);
        }}

        function onRazorpayPaymentSuccess(data) {{
            if (activeRazorpayPollInterval) {{
                clearInterval(activeRazorpayPollInterval);
                activeRazorpayPollInterval = null;
            }}

            currentRazorpayTxnId = data.payment_id || ('pay_' + Date.now());

            const statusBox = document.getElementById('rzpLiveStatusBox');
            statusBox.style.background = '#ECFDF5';
            statusBox.style.borderColor = '#10B981';
            document.getElementById('rzpStatusText').innerHTML = `
                <div style="color: #065F46; font-size: 0.95rem; font-weight: 800; text-align: center;">
                    <div style="font-size: 1.4rem; margin-bottom: 2px;">✅</div>
                    <div>Transaction Successfully Done!</div>
                    <div style="font-size: 0.76rem; font-weight: 600; color: #047857; margin-top: 4px;">TXN ID: <code>' + currentRazorpayTxnId + '</code></div>
                </div>
            `;

            document.getElementById('rzpQrCardContainer').style.opacity = '0.35';
            document.getElementById('rzpSuccessActions').style.display = 'flex';
        }}

        function completeOnlineCheckoutAndPrint() {{
            closeRazorpayModal();
            checkoutSale('RAZORPAY_UPI', currentRazorpayTxnId);
        }}

        function closeRazorpayModal() {{
            if (activeRazorpayPollInterval) {{
                clearInterval(activeRazorpayPollInterval);
                activeRazorpayPollInterval = null;
            }}
            currentRazorpayPlinkId = null;
            document.getElementById('razorpayPaymentModal').style.display = 'none';
        }}

        async function simulateRazorpayApproval() {{
            if (!currentRazorpayPlinkId) return;
            try {{
                const res = await fetch('/api/pos/check-payment-status/?plink_id=' + encodeURIComponent(currentRazorpayPlinkId) + '&simulate=true');
                const data = await res.json();
                if (data.success) {{
                    onRazorpayPaymentSuccess(data);
                }}
            }} catch (err) {{
                alert('Simulation error: ' + err.message);
            }}
        }}

        async function checkoutSale(explicitPayMethod = null, explicitTxnId = null) {{
            if (cart.length === 0) {{
                alert('Please add at least one product to the cart before checkout.');
                return;
            }}

            const chosenPayMethod = explicitPayMethod || currentPosPaymentMode || 'CASH';
            const payMethodDisplay = (chosenPayMethod === 'RAZORPAY_UPI' || chosenPayMethod === 'ONLINE') ? 'Razorpay Online (UPI)' : 'Cash';
            const transactionRef = explicitTxnId || null;

            let billNum = 'SB-BILL-' + Math.floor(100000 + Math.random() * 900000);
            const now = new Date().toLocaleString();
            let subtotal = 0;
            let tax = 0;
            let receiptItems = '';

            cart.forEach(item => {{
                const itemTotal = item.price * item.qty;
                subtotal += itemTotal;
                tax += itemTotal * (item.tax_rate / 100);
                receiptItems += `${{item.name.padEnd(16).substring(0, 16)}} ${{String(item.qty).padStart(2)}}  ${{item.price.toFixed(0).padStart(4)}}  ${{itemTotal.toFixed(0).padStart(5)}}\\n`;
            }});

            const finalTotal = subtotal + tax;
            const custName = attachedCustomer ? attachedCustomer.name : 'Walk-in Guest';
            const custPhone = attachedCustomer ? attachedCustomer.phone : 'N/A';
            const custCode = attachedCustomer ? attachedCustomer.code : 'WALK-IN';
            const custEmail = attachedCustomer ? attachedCustomer.email : '';
            const curShopCode = (activeShop && activeShop.code) ? activeShop.code : 'SB-SHOP-001';
            const curShopId = (activeShop && activeShop.id) ? activeShop.id : null;
            const curCashier = currentCashierName || 'Cashier';
            const curCashierId = currentCashierId || 'STAFF';

            let checkoutData = null;

            try {{
                const res = await fetch('/api/pos/checkout/', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{
                        shop_code: curShopCode,
                        shop_id: curShopId,
                        cashier_id: curCashierId,
                        cashier_name: curCashier,
                        payment_method: chosenPayMethod,
                        transaction_id: transactionRef,
                        customer_id: attachedCustomer ? attachedCustomer.id : null,
                        items: cart.map(it => ({{ product_id: it.id, quantity: it.qty }}))
                    }})
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    checkoutData = data;
                    billNum = data.bill_number || billNum;
                    if (data.updated_stocks) {{
                        Object.entries(data.updated_stocks).forEach(([pid, newStock]) => {{
                            const prod = productsData.find(p => String(p.id) === String(pid));
                            if (prod) prod.stock = newStock;
                        }});
                        renderPosGrid();
                    }}
                    renderLowStockNotifications(true);
                }}
            }} catch (e) {{
                console.warn('Offline checkout fallback:', e);
                cart.forEach(it => {{
                    const prod = productsData.find(p => String(p.id) === String(it.id));
                    if (prod) prod.stock = Math.max(0, parseFloat(prod.stock) - it.qty);
                }});
                renderPosGrid();
                renderLowStockNotifications(true);
            }}

            const shopOwnerName = (checkoutData && checkoutData.owner_name) || (activeShop && activeShop.owner_name) || (activeShopOwner && activeShopOwner.name) || 'Store Owner';
            const billedByCashier = (checkoutData && checkoutData.cashier_name) || curCashier;
            const billedByCashierId = (checkoutData && checkoutData.cashier_id) || curCashierId;
            const finalCustomerEmail = (checkoutData && checkoutData.email_recipient) ? checkoutData.email_recipient : custEmail;
            const finalTxnId = (checkoutData && checkoutData.transaction_id) || transactionRef || 'CASH-SETTLED';

            // Prepend transaction to local recent sales & refresh isolated stats
            recentSalesData.unshift({{
                bill_number: billNum,
                shop_name: (activeShop && activeShop.name) ? activeShop.name : 'Smart Bazaar',
                shop_code: curShopCode,
                shop_owner: shopOwnerName,
                cashier_name: billedByCashier,
                cashier_id: billedByCashierId,
                customer_name: custName,
                customer_phone: custPhone,
                customer_email: finalCustomerEmail,
                final_total: finalTotal,
                payment_method: payMethodDisplay,
                transaction_id: finalTxnId,
                created_at: 'Just Now'
            }});
            if (activeShop) {{
                setActiveShopContext(activeShop);
            }}

            const receiptStoreName = ((activeShop && activeShop.name) ? activeShop.name : 'SMART BAZAAR').toUpperCase();
            const receiptStoreAddr = (activeShop && activeShop.address) ? activeShop.address : 'Station Road, Kolkata - 700001';
            const receiptStorePhone = (activeShop && activeShop.phone) ? activeShop.phone : '+91 96922 76657';
            const receiptStoreCode = curShopCode;

            const receiptText = 
`================================
${{receiptStoreName.padStart(Math.floor((32 + Math.min(32, receiptStoreName.length)) / 2)).padEnd(32)}}
${{receiptStoreAddr.substring(0, 32).padStart(Math.floor((32 + Math.min(32, receiptStoreAddr.length)) / 2)).padEnd(32)}}
Phone: ${{receiptStorePhone}}
Store ID: ${{receiptStoreCode}}
================================
Shop Owner: ${{shopOwnerName}}
Cashier   : ${{billedByCashier}} (${{billedByCashierId}})
Bill No   : ${{billNum}}
Date      : ${{now}}
Customer  : ${{custName}}
Phone     : ${{custPhone}}
Code      : ${{custCode}}
${{finalCustomerEmail ? `Gmail     : ${{finalCustomerEmail}}\\n` : ''}}Payment   : ${{payMethodDisplay}}
${{finalTxnId ? `Txn Ref   : ${{finalTxnId}}\\n` : ''}}--------------------------------
ITEM             QTY  RATE  TOTAL
--------------------------------
${{receiptItems}}--------------------------------
Subtotal:              ₹${{subtotal.toFixed(2)}}
GST Amount:            ₹${{tax.toFixed(2)}}
================================
TOTAL AMOUNT:          ₹${{finalTotal.toFixed(2)}}
================================
Status      : SUCCESS (PAID)
--------------------------------
${{checkoutData && checkoutData.email_sent ? ' [✓] Official Tax Invoice & PDF \\n sent to Customer Gmail!\\n--------------------------------\\n' : ''}}   Thank You for Shopping at   
   ${{receiptStoreName}}!
   Visit Again & Earn Points   
================================
`;

            // 1. Render receipt text
            document.getElementById('receiptContent').innerText = receiptText;

            // 2. Set authentic store watermark background if store owner uploaded logo
            const logoUrl = (checkoutData && checkoutData.shop_logo_url) || (activeShop && activeShop.logo_url) || '';
            const receiptBox = document.getElementById('receiptContainerBox');
            if (receiptBox) {{
                if (logoUrl) {{
                    receiptBox.style.backgroundImage = `url('${{logoUrl}}')`;
                    receiptBox.style.backgroundRepeat = 'no-repeat';
                    receiptBox.style.backgroundPosition = 'center';
                    receiptBox.style.backgroundSize = '200px';
                    receiptBox.style.backgroundColor = 'rgba(255, 253, 249, 0.92)';
                    receiptBox.style.backgroundBlendMode = 'overlay';
                }} else {{
                    receiptBox.style.backgroundImage = 'none';
                    receiptBox.style.backgroundColor = '#FFFDF9';
                }}
            }}

            // 3. Render email & PDF dispatch status banner
            const banner = document.getElementById('receiptEmailStatusBanner');
            if (banner) {{
                if (checkoutData && checkoutData.email_sent) {{
                    banner.style.display = 'flex';
                    banner.style.alignItems = 'center';
                    banner.style.gap = '8px';
                    banner.style.background = '#ECFDF5';
                    banner.style.border = '1.5px solid #10B981';
                    banner.style.color = '#065F46';
                    banner.innerHTML = `<span style="font-size:1.2rem;">✉️</span><div><strong>Invoice & PDF Dispatched!</strong><br><span style="font-size:0.75rem;">Official Tax Invoice with authentic store watermark was sent to <strong>${{checkoutData.email_recipient}}</strong> via official Google Gmail API.</span></div>`;
                }} else if (finalCustomerEmail) {{
                    banner.style.display = 'block';
                    banner.style.background = '#FFFBEB';
                    banner.style.border = '1px solid #F59E0B';
                    banner.style.color = '#92400E';
                    banner.innerHTML = `⚠️ PDF receipt generated. Email dispatch status: ${{checkoutData && checkoutData.email_error ? checkoutData.email_error : 'Queued'}}.`;
                }} else {{
                    banner.style.display = 'none';
                }}
            }}

            document.getElementById('receiptModal').style.display = 'flex';
            cart = [];
            renderCart();
            const fb = document.getElementById('barcodeFeedbackBanner');
            if (fb) fb.style.display = 'none';
        }}

        function closeReceipt() {{
            document.getElementById('receiptModal').style.display = 'none';
            resetCustomerLookup();
        }}

        function renderCustomerBills() {{
            const tbody = document.getElementById('customerBillsTbody');
            tbody.innerHTML = '';
            recentSalesData.forEach(s => {{
                tbody.innerHTML += `
                    <tr>
                        <td><code>${{s.bill_number}}</code></td>
                        <td><strong>${{s.shop_name}}</strong></td>
                        <td style="color: var(--success); font-weight: 700;">₹${{s.final_total.toFixed(2)}}</td>
                        <td><span class="badge badge-purple">${{s.payment_method}}</span></td>
                        <td>${{s.created_at}}</td>
                    </tr>
                `;
            }});
        }}


        // ======================= MOBILE-FIRST BOTTOM NAVIGATION & POS HELPERS =======================
        let activeMobileNavTab = 'home';
        let currentReceiptWidth = 58;
        let selectedDrawerPaymentMethod = 'CASH';

        function renderMobileBottomNav(role, activeTab) {{
            const nav = document.getElementById('mobileBottomNav');
            if (!nav) return;
            if (!role || role === 'GUEST' || role === 'CUSTOMER') {{
                nav.style.display = 'none';
                return;
            }}
            nav.style.display = 'flex';
            activeTab = activeTab || activeMobileNavTab;
            activeMobileNavTab = activeTab;

            if (role === 'SUPER_ADMIN') {{
                nav.innerHTML = `
                    <button type="button" class="bottom-nav-item ${{activeTab === 'shops' ? 'active' : ''}}" onclick="mobileNavSuper('shops')">
                        <span class="nav-icon">🏢</span>
                        <span>Shops</span>
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'add' ? 'active' : ''}}" onclick="openSuperAdminAddModal()">
                        <span class="nav-icon">➕</span>
                        <span>Add Shop</span>
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'stats' ? 'active' : ''}}" onclick="mobileNavSuper('stats')">
                        <span class="nav-icon">📊</span>
                        <span>Stats</span>
                    </button>
                    <button type="button" class="bottom-nav-item" onclick="logout()">
                        <span class="nav-icon">🚪</span>
                        <span>Sign Out</span>
                    </button>
                `;
            }} else if (role === 'SHOP_OWNER') {{
                nav.innerHTML = `
                    <button type="button" class="bottom-nav-item ${{activeTab === 'overview' ? 'active' : ''}}" onclick="mobileNavOwner('overview')">
                        <span class="nav-icon">🏠</span>
                        <span>Home</span>
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'products' ? 'active' : ''}}" onclick="mobileNavOwner('products')">
                        <span class="nav-icon">📦</span>
                        <span>Products</span>
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'pos' ? 'active' : ''}}" onclick="mobileNavOwner('pos')">
                        <span class="nav-icon">🛒</span>
                        <span>POS Bill</span>
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'sales' ? 'active' : ''}}" onclick="mobileNavOwner('sales')">
                        <span class="nav-icon">🧾</span>
                        <span>Receipts</span>
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'settings' ? 'active' : ''}}" onclick="mobileNavOwner('settings')">
                        <span class="nav-icon">⚙️</span>
                        <span>Profile</span>
                    </button>
                `;
            }} else if (role === 'WORKER') {{
                const cartQty = (cart || []).reduce((sum, item) => sum + item.qty, 0);
                nav.innerHTML = `
                    <button type="button" class="bottom-nav-item ${{activeTab === 'pos' ? 'active' : ''}}" onclick="mobileNavWorker('pos')">
                        <span class="nav-icon">🛒</span>
                        <span>Terminal</span>
                    </button>
                    <button type="button" class="bottom-nav-item" onclick="openWebcamScannerModal()">
                        <span class="nav-icon">📷</span>
                        <span>Scan</span>
                    </button>
                    <button type="button" class="bottom-nav-item" onclick="openMobileCartDrawer()">
                        <span class="nav-icon">🛍️</span>
                        <span>Cart</span>
                        ${{cartQty > 0 ? `<span class="bottom-nav-badge">${{cartQty}}</span>` : ''}}
                    </button>
                    <button type="button" class="bottom-nav-item ${{activeTab === 'history' ? 'active' : ''}}" onclick="mobileNavWorker('history')">
                        <span class="nav-icon">🧾</span>
                        <span>Receipts</span>
                    </button>
                    <button type="button" class="bottom-nav-item" onclick="logout()">
                        <span class="nav-icon">👤</span>
                        <span>Exit</span>
                    </button>
                `;
            }}
        }}

        function mobileNavSuper(tab) {{
            activeMobileNavTab = tab;
            showView('superAdminView');
            renderMobileBottomNav('SUPER_ADMIN', tab);
            if (tab === 'shops') {{
                const el = document.getElementById('superAdminOwnersTable');
                if (el) el.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
            }} else if (tab === 'stats') {{
                window.scrollTo({{ top: 0, behavior: 'smooth' }});
            }}
        }}

        function mobileNavOwner(section) {{
            activeMobileNavTab = section;
            if (section === 'pos') {{
                showView('workerPosView');
                initPos();
                renderMobileBottomNav('SHOP_OWNER', 'pos');
                return;
            }}
            showView('adminView');
            switchAdminSection(section);
            renderMobileBottomNav('SHOP_OWNER', section);
        }}

        function mobileNavWorker(tab) {{
            activeMobileNavTab = tab;
            showView('workerPosView');
            renderMobileBottomNav('WORKER', tab);
            if (tab === 'history') {{
                const hist = document.getElementById('customerBillsTbody');
                if (hist) hist.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            }}
        }}

        // ======================= MOBILE CART DRAWER (Bottom Sheet) =======================
        function openMobileCartDrawer() {{
            const drawer = document.getElementById('mobileCartDrawer');
            if (!drawer) return;
            renderDrawerCartItems();
            drawer.style.display = 'flex';
            if (window.history && window.history.pushState) {{
                window.history.pushState({{ drawerOpen: true }}, '');
            }}
        }}

        function closeMobileCartDrawer() {{
            const drawer = document.getElementById('mobileCartDrawer');
            if (drawer) drawer.style.display = 'none';
        }}

        function renderDrawerCartItems() {{
            const container = document.getElementById('drawerCartItems');
            const badge = document.getElementById('drawerCartBadge');
            const totalQty = (cart || []).reduce((sum, item) => sum + item.qty, 0);
            if (badge) badge.innerText = `${{totalQty}} Items`;

            if (!container) return;
            if (!cart || cart.length === 0) {{
                container.innerHTML = `
                    <div style="text-align: center; padding: 32px 14px; color: #64748B;">
                        <div style="font-size: 2.2rem; margin-bottom: 8px;">🛒</div>
                        <strong style="color: #0F172A; display: block; margin-bottom: 4px;">Your Cart is Empty</strong>
                        <span style="font-size: 0.82rem;">Scan a barcode or tap + Add on any product to start a bill.</span>
                    </div>
                `;
                document.getElementById('drawerSubtotal').innerText = '₹0.00';
                document.getElementById('drawerTax').innerText = '₹0.00';
                document.getElementById('drawerGrandTotal').innerText = '₹0.00';
                return;
            }}

            let subtotal = 0;
            let tax = 0;
            let html = '<div style="display: flex; flex-direction: column; gap: 8px;">';

            cart.forEach(item => {{
                const itemTotal = item.price * item.qty;
                const itemTax = itemTotal * (item.tax_rate / 100);
                subtotal += itemTotal;
                tax += itemTax;

                html += `
                    <div style="background: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 12px; padding: 10px 12px; display: flex; justify-content: space-between; align-items: center;">
                        <div style="flex: 1; padding-right: 8px;">
                            <strong style="font-size: 0.88rem; color: #0F172A; display: block;">${{item.name}}</strong>
                            <span style="font-size: 0.75rem; color: #64748B;">₹${{item.price.toFixed(2)}} each</span>
                        </div>
                        <div style="display: flex; align-items: center; gap: 6px;">
                            <button type="button" onclick="updateCartQty('${{item.id}}', -1); renderDrawerCartItems();" style="width: 32px; height: 32px; border-radius: 8px; border: 1px solid #CBD5E1; background: white; font-weight: 800; color: #0F5132; cursor: pointer; font-size: 1rem;">&minus;</button>
                            <span style="font-weight: 800; min-width: 20px; text-align: center; font-size: 0.95rem;">${{item.qty}}</span>
                            <button type="button" onclick="updateCartQty('${{item.id}}', 1); renderDrawerCartItems();" style="width: 32px; height: 32px; border-radius: 8px; border: 1px solid #0F5132; background: #DCFCE7; font-weight: 800; color: #0F5132; cursor: pointer; font-size: 1rem;">+</button>
                            <span style="font-weight: 800; font-size: 0.92rem; color: #0F5132; margin-left: 6px; min-width: 58px; text-align: right;">₹${{itemTotal.toFixed(2)}}</span>
                        </div>
                    </div>
                `;
            }});
            html += '</div>';
            container.innerHTML = html;

            const grand = subtotal + tax;
            document.getElementById('drawerSubtotal').innerText = '₹' + subtotal.toFixed(2);
            document.getElementById('drawerTax').innerText = '₹' + tax.toFixed(2);
            document.getElementById('drawerGrandTotal').innerText = '₹' + grand.toFixed(2);
        }}

        function selectDrawerPayment(mode) {{
            selectedDrawerPaymentMethod = mode;
            ['payBtnCash', 'payBtnUPI', 'payBtnCard'].forEach(btnId => {{
                const b = document.getElementById(btnId);
                if (!b) return;
                const match = (mode === 'CASH' && btnId === 'payBtnCash') ||
                              (mode === 'UPI' && btnId === 'payBtnUPI') ||
                              (mode === 'CARD' && btnId === 'payBtnCard');
                if (match) {{
                    b.style.background = '#0F5132';
                    b.style.color = '#FFFFFF';
                    b.style.borderColor = '#0F5132';
                }} else {{
                    b.style.background = 'transparent';
                    b.style.color = '#0F5132';
                    b.style.borderColor = '#0F5132';
                }}
            }});
        }}

        function checkoutFromDrawer() {{
            if (!cart || cart.length === 0) {{
                alert('Your cart is empty. Please add items before checking out.');
                return;
            }}
            closeMobileCartDrawer();
            checkoutBill();
        }}

        // ======================= THERMAL RECEIPT ACTIONS =======================
        function setReceiptWidth(mm) {{
            currentReceiptWidth = mm;
            const b58 = document.getElementById('btnReceipt58');
            const b80 = document.getElementById('btnReceipt80');
            const box = document.getElementById('receiptContainerBox');
            const badge = document.getElementById('receiptWidthBadge');

            if (mm === 58) {{
                if (b58) {{ b58.style.background = '#0F5132'; b58.style.color = 'white'; }}
                if (b80) {{ b80.style.background = 'transparent'; b80.style.color = '#475569'; }}
                if (box) box.style.maxWidth = '310px';
                if (badge) badge.innerText = '58mm Mobile Thermal';
            }} else {{
                if (b58) {{ b58.style.background = 'transparent'; b58.style.color = '#475569'; }}
                if (b80) {{ b80.style.background = '#0F5132'; b80.style.color = 'white'; }}
                if (box) box.style.maxWidth = '420px';
                if (badge) badge.innerText = '80mm Counter Thermal';
            }}
        }}

        function printThermalReceipt() {{
            const receiptText = document.getElementById('receiptContent').innerText;
            const printWin = window.open('', '_blank', 'width=460,height=650');
            if (!printWin) {{
                window.print();
                return;
            }}
            const w = currentReceiptWidth === 80 ? '76mm' : '54mm';
            const logoUrl = (activeShop && activeShop.logo_url) ? activeShop.logo_url : '';
            printWin.document.write(`
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Official Store Receipt - ${{activeShop ? activeShop.name : 'Smart Bazaar'}}</title>
                    <style>
                        @page {{ size: ${{w}} auto; margin: 0; }}
                        body {{
                            width: ${{w}};
                            margin: 0;
                            padding: 8px;
                            font-family: 'Courier New', monospace;
                            font-size: 11px;
                            line-height: 1.35;
                            color: #000;
                            white-space: pre-wrap;
                            position: relative;
                        }}
                        .print-watermark {{
                            position: fixed;
                            top: 45%;
                            left: 50%;
                            transform: translate(-50%, -50%);
                            width: 65%;
                            opacity: 0.10;
                            pointer-events: none;
                            z-index: 0;
                        }}
                        .print-content {{
                            position: relative;
                            z-index: 1;
                        }}
                    </style>
                </head>
                <body>
                    ${{logoUrl ? `<img src="${{logoUrl}}" class="print-watermark" alt="Logo Watermark" />` : ''}}
                    <div class="print-content">${{receiptText}}</div>
                </body>
                </html>
            `);
            printWin.document.close();
            printWin.focus();
            setTimeout(() => {{
                printWin.print();
                printWin.close();
            }}, 300);
        }}

        async function handleShopLogoUpload(e) {{
            const file = e.target.files && e.target.files[0];
            if (!file) return;

            const fd = new FormData();
            fd.append('logo', file);
            if (activeShop && activeShop.code) {{
                fd.append('shop_code', activeShop.code);
            }}
            if (activeShop && activeShop.id) {{
                fd.append('shop_id', activeShop.id);
            }}

            try {{
                const res = await fetch('/api/admin/shop/logo/', {{
                    method: 'POST',
                    body: fd
                }});
                const data = await res.json();
                if (res.ok && data.success) {{
                    if (activeShop) {{
                        activeShop.logo_url = data.logo_url;
                    }}
                    const logoImg = document.getElementById('shopLogoHeaderImg');
                    const logoPh = document.getElementById('shopLogoPlaceholder');
                    if (logoImg) {{
                        logoImg.src = data.logo_url;
                        logoImg.style.display = 'block';
                    }}
                    if (logoPh) {{
                        logoPh.style.display = 'none';
                    }}
                    alert('✓ Store brand logo uploaded successfully! It is now active as the official watermark on customer receipts and PDF invoices.');
                }} else {{
                    alert('Failed to upload store logo: ' + (data.error || 'Server error'));
                }}
            }} catch (err) {{
                alert('Network error while uploading store logo: ' + err.message);
            }}
        }}

        function downloadThermalReceipt() {{
            const receiptText = document.getElementById('receiptContent').innerText;
            const blob = new Blob([receiptText], {{ type: 'text/plain;charset=utf-8' }});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `SmartBazaar_Receipt_${{Date.now()}}.txt`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);
        }}

        function copyReceiptText() {{
            const receiptText = document.getElementById('receiptContent').innerText;
            navigator.clipboard.writeText(receiptText).then(() => {{
                alert('✓ Receipt copied to clipboard!');
            }}).catch(() => {{
                alert('Copied to clipboard.');
            }});
        }}

        async function shareReceipt() {{
            const receiptText = document.getElementById('receiptContent').innerText;
            const storeName = activeShopContext ? activeShopContext.name : 'Smart Bazaar';
            const shareData = {{
                title: `${{storeName}} - Official Receipt`,
                text: receiptText
            }};

            if (navigator.share) {{
                try {{
                    await navigator.share(shareData);
                }} catch (err) {{
                    if (err.name !== 'AbortError') {{
                        openWhatsAppShare(receiptText);
                    }}
                }}
            }} else {{
                openWhatsAppShare(receiptText);
            }}
        }}

        function openWhatsAppShare(text) {{
            const url = 'https://api.whatsapp.com/send?text=' + encodeURIComponent(text);
            window.open(url, '_blank');
        }}

        // ======================= PWA SERVICE WORKER & ANDROID BACK BUTTON =======================
        if ('serviceWorker' in navigator) {{
            window.addEventListener('load', () => {{
                navigator.serviceWorker.register('/sw.js').catch(() => {{}});
            }});
        }}

        // Android Hardware Back Button Handling
        window.addEventListener('popstate', (e) => {{
            const modalIds = ['receiptModal', 'barcodeTagModal', 'webcamScannerModal', 'workerResetPassModal', 'superAdminResetModal', 'superAdminEditModal', 'mobileCartDrawer'];
            let anyClosed = false;
            modalIds.forEach(id => {{
                const el = document.getElementById(id);
                if (el && el.style.display && el.style.display !== 'none') {{
                    el.style.display = 'none';
                    anyClosed = true;
                }}
            }});
            if (anyClosed) {{
                e.preventDefault();
            }}
        }});

        // Auto-scan support + automatic < 15 low-stock alert sync for Shop Owner & Cashier dashboards
        window.addEventListener('DOMContentLoaded', () => {{
            renderLowStockNotifications(false);
            setInterval(() => syncLowStockAlertsFromServer(true), 12000);

            // Enter key support for login form
            ['staffUsername', 'staffPassword'].forEach(id => {{
                const el = document.getElementById(id);
                if (el) {{
                    el.addEventListener('keydown', (e) => {{
                        if (e.key === 'Enter') handleStaffLogin();
                    }});
                }}
            }});

            const params = new URLSearchParams(window.location.search);
            const autoCode = params.get('autoScan') || sessionStorage.getItem('autoScanBarcode');
            if (autoCode) {{
                sessionStorage.removeItem('autoScanBarcode');
                setAuthUser('Arun Kumar', 'Cashier', 'badge-green', 'workerPosView');
                initPos();
                continueAsGuest();
                setTimeout(() => {{
                    simulateBarcodeScan(autoCode);
                }}, 450);
            }}
        }});
    </script>
</body>
</html>
"""
    return HttpResponse(html)

# ======================= ADMIN: PRODUCT API ENDPOINTS =======================

@csrf_exempt
def api_admin_add_product(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body) if (request.body and request.body.startswith(b'{')) else request.POST.dict()
        caller_role = data.get('caller_role') or data.get('role')
        owner_username = data.get('owner_username', '').strip()
        shop_code = data.get('shop_code', '').strip()
        user = getattr(request, 'user', None)

        # Strict RBAC: Super Admin is strictly prohibited from adding products
        if caller_role == 'SUPER_ADMIN' or (user and getattr(user, 'is_authenticated', False) and getattr(user, 'role', '') == User.Role.SUPER_ADMIN):
            return JsonResponse({
                'error': 'Permission Denied: Super Admin is strictly prohibited from adding products. Products can only be added and managed by Shop Owners.'
            }, status=403)

        # Identify the Shop Owner's specific shop (prioritize explicit shop_code from active UI session)
        shop = None
        if shop_code:
            shop = Shop.objects.using('default').filter(code__iexact=shop_code).first()
        if not shop and owner_username:
            shop = Shop.objects.using('default').filter(owner__username__iexact=owner_username).first()
        if not shop and user and getattr(user, 'is_authenticated', False):
            if hasattr(user, 'owned_shops') and user.owned_shops.exists():
                shop = user.owned_shops.first()
            elif getattr(user, 'role', '') == User.Role.SHOP_OWNER:
                shop = Shop.objects.using('default').filter(owner=user).first()

        if not shop:
            shop = Shop.objects.using('default').filter(owner__role=User.Role.SHOP_OWNER).first() or Shop.objects.using('default').first()

        if not shop:
            return JsonResponse({'error': 'No shop registered for this Shop Owner'}, status=400)

        # Proactively ensure tenant DB connection and Shop/Owner profile exist
        from apps.core.database_provisioner import resolve_shop_db_alias_for_user, sync_shop_and_owner_to_tenant_db
        target_db = resolve_shop_db_alias_for_user(user if (user and user.is_authenticated) else None, shop.code)
        
        # Ensure SQLite foreign keys cannot block cross-database multi-tenant operations
        from django.db import connections, connection
        for conn_alias in ['default', target_db]:
            if conn_alias and conn_alias in connections:
                try:
                    c = connections[conn_alias]
                    if c.vendor == 'sqlite':
                        with c.cursor() as cur:
                            cur.execute("PRAGMA foreign_keys = OFF;")
                except Exception:
                    pass

        if target_db and target_db != 'default':
            try:
                sync_shop_and_owner_to_tenant_db(shop, target_db)
            except Exception as sync_e:
                logger.warning(f"Note: Shop sync to tenant DB warning: {sync_e}")

        name = data.get('name')
        if not name:
            return JsonResponse({'error': 'Product name is required'}, status=400)

        category_name = data.get('category_name', 'General')
        barcode = data.get('barcode', '').strip()
        price = Decimal(str(data.get('selling_price', 0)))
        mrp = Decimal(str(data.get('mrp', price)))
        qty = Decimal(str(data.get('quantity', 0)))
        unit = data.get('unit', 'PCS')

        sku = f"SKU-{secrets.randbelow(90000) + 10000}"
        if not barcode:
            barcode = f"890{secrets.randbelow(9000000000) + 1000000000}"

        # 1. Primary write to 'default' central database
        cat_default, _ = Category.objects.using('default').get_or_create(shop=shop, name=category_name)
        product = Product.objects.using('default').create(
            shop=shop,
            category=cat_default,
            name=name,
            sku=sku,
            selling_price=price,
            mrp=mrp,
            unit=unit
        )
        ProductBarcode.objects.using('default').create(product=product, barcode=barcode, is_primary=True)
        inv_default, _ = Inventory.objects.using('default').get_or_create(shop=shop, product=product, defaults={'current_stock': qty, 'reorder_level': LOW_STOCK_THRESHOLD})
        inv_default.current_stock = qty
        inv_default.save(using='default')

        StockTransaction.objects.using('default').create(
            shop=shop,
            product=product,
            tx_type=StockTransaction.TxType.PURCHASE,
            quantity=qty,
            balance_after=qty,
            reference_id=f"OPENING-{sku}",
            notes=f"Opening stock entry for shop {shop.code} by Shop Owner"
        )

        # 2. Mirror into tenant database for strict data isolation
        if target_db and target_db != 'default' and target_db in connections:
            try:
                cat_tenant, _ = Category.objects.using(target_db).get_or_create(shop=shop, name=category_name)
                prod_tenant = Product.objects.using(target_db).create(
                    id=product.id,
                    shop=shop,
                    category=cat_tenant,
                    name=name,
                    sku=sku,
                    selling_price=price,
                    mrp=mrp,
                    unit=unit
                )
                ProductBarcode.objects.using(target_db).create(product=prod_tenant, barcode=barcode, is_primary=True)
                inv_tenant, _ = Inventory.objects.using(target_db).get_or_create(shop=shop, product=prod_tenant, defaults={'current_stock': qty, 'reorder_level': LOW_STOCK_THRESHOLD})
                inv_tenant.current_stock = qty
                inv_tenant.save(using=target_db)
            except Exception as tenant_err:
                logger.warning(f"Note: Could not mirror product to tenant {target_db}: {tenant_err}")

        return JsonResponse({
            'success': True,
            'product': {
                'id': str(product.id),
                'name': product.name,
                'barcode': barcode,
                'selling_price': float(product.selling_price),
                'mrp': float(product.mrp),
                'tax_rate': float(product.tax_rate),
                'unit': product.unit,
                'stock': float(qty),
                'category': cat_default.name,
                'shop_id': str(shop.id),
                'shop_code': shop.code
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def api_admin_delete_product(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body) if (request.body and request.body.startswith(b'{')) else request.POST.dict()
        caller_role = data.get('caller_role') or data.get('role')
        user = getattr(request, 'user', None)
        if caller_role == 'SUPER_ADMIN' or (user and getattr(user, 'is_authenticated', False) and getattr(user, 'role', '') == User.Role.SUPER_ADMIN):
            return JsonResponse({'error': 'Permission Denied: Super Admin cannot delete shop products.'}, status=403)
        product_id = data.get('product_id')
        Product.objects.using('default').filter(id=product_id).delete()
        from django.db import connections
        for alias in list(connections.databases.keys()):
            if alias != 'default':
                try:
                    Product.objects.using(alias).filter(id=product_id).delete()
                except Exception:
                    pass
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def api_admin_update_product(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body) if (request.body and request.body.startswith(b'{')) else request.POST.dict()
        caller_role = data.get('caller_role') or data.get('role')
        user = getattr(request, 'user', None)
        if caller_role == 'SUPER_ADMIN' or (user and getattr(user, 'is_authenticated', False) and getattr(user, 'role', '') == User.Role.SUPER_ADMIN):
            return JsonResponse({'error': 'Permission Denied: Super Admin cannot update shop products.'}, status=403)
        product_id = data.get('product_id')
        price = data.get('selling_price')
        qty = data.get('quantity')

        from django.db import connections
        for alias in list(connections.databases.keys()):
            try:
                prod = Product.objects.using(alias).filter(id=product_id).first()
                if prod:
                    if price is not None:
                        prod.selling_price = Decimal(str(price))
                        prod.save(using=alias)
                    if qty is not None:
                        inv, _ = Inventory.objects.using(alias).get_or_create(shop=prod.shop, product=prod)
                        inv.current_stock = Decimal(str(qty))
                        inv.save(using=alias)
            except Exception:
                pass

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

# ======================= ADMIN: WORKER API ENDPOINTS =======================


@csrf_exempt
def api_admin_send_worker_otp(request):
    from apps.core.workflow_views import api_shop_employees_send_otp
    return api_shop_employees_send_otp(request)

@csrf_exempt
def api_admin_add_worker(request):
    from apps.core.workflow_views import api_shop_employees_create
    return api_shop_employees_create(request)

@csrf_exempt
def api_admin_reset_worker_password(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        new_password = data.get('new_password', '').strip()
        if not new_password or len(new_password) < 4:
            return JsonResponse({'error': 'Password must be at least 4 characters long.'}, status=400)

        user = User.objects.get(id=user_id)
        user.set_password(new_password)
        user.save()

        return JsonResponse({
            'success': True,
            'message': f"Password for worker '{user.username}' ({user.first_name or user.username}) updated successfully.",
            'worker_id': user.username
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def api_admin_toggle_worker(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        user = User.objects.get(id=user_id)
        user.is_active = not user.is_active
        user.save()
        return JsonResponse({'success': True, 'is_active': user.is_active})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def api_admin_delete_worker(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        user_id = data.get('user_id')
        ShopMembership.objects.filter(user_id=user_id).delete()
        User.objects.filter(id=user_id).update(is_active=False)
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)



# ======================= ADMIN: SHOP LOGO & PROFILE SETTINGS =======================

@csrf_exempt
def api_admin_upload_shop_logo(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        logo_file = request.FILES.get('logo')
        if not logo_file:
            return JsonResponse({'error': 'No image file provided'}, status=400)
        
        shop_code = request.POST.get('shop_code') or request.POST.get('shop_id')
        owner_username = request.POST.get('owner_username')
        shop = None
        if shop_code:
            shop = Shop.objects.filter(code__iexact=shop_code).first() or Shop.objects.filter(id=shop_code).first()
        if not shop and owner_username:
            shop = Shop.objects.filter(owner__username=owner_username).first()
        if not shop:
            shop = Shop.objects.first()
        
        if not shop:
            return JsonResponse({'error': 'Shop not found'}, status=404)
        
        shop.logo = logo_file
        shop.save()
        
        logo_url = shop.logo.url if shop.logo else ''
        return JsonResponse({'success': True, 'logo_url': logo_url, 'shop_code': shop.code})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

@csrf_exempt
def api_admin_update_shop_profile(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body) if (request.body and request.body.startswith(b'{')) else request.POST.dict()
        shop_code = data.get('shop_code') or data.get('shop_id')
        owner_username = data.get('owner_username')

        shop = None
        if shop_code:
            shop = Shop.objects.filter(code__iexact=shop_code).first() or Shop.objects.filter(id=shop_code).first()
        if not shop and owner_username:
            shop = Shop.objects.filter(owner__username=owner_username).first()
        if not shop:
            shop = Shop.objects.first()

        if not shop:
            return JsonResponse({'error': 'Shop not found'}, status=404)

        if data.get('name'):
            shop.name = data.get('name').strip()
        if data.get('address'):
            shop.address = data.get('address').strip()
        if data.get('city'):
            shop.city = data.get('city').strip()
        if data.get('phone'):
            shop.phone = data.get('phone').strip()
        if data.get('upi_vpa'):
            shop.upi_vpa = data.get('upi_vpa').strip()

        shop.save()

        return JsonResponse({
            'success': True,
            'shop': {
                'id': str(shop.id),
                'name': shop.name,
                'code': shop.code,
                'city': shop.city,
                'address': shop.address or f"{shop.city}, West Bengal",
                'phone': shop.phone,
                'upi_vpa': shop.upi_vpa or 'smartbazaar@okaxis',
                'owner_name': shop.owner.get_full_name() or shop.owner.username if shop.owner else '',
                'owner_phone': shop.owner.phone_number if shop.owner else '',
                'logo_url': shop.logo.url if shop.logo else ''
            }
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ======================= SUPER ADMIN API ENDPOINTS (SHOP OWNERS & GMAIL OTP) =======================

@csrf_exempt
def api_superadmin_send_owner_otp(request):
    from apps.core.workflow_views import api_superadmin_owners_send_otp
    return api_superadmin_owners_send_otp(request)


@csrf_exempt
def api_superadmin_add_owner(request):
    from apps.core.workflow_views import api_superadmin_owners_create
    return api_superadmin_owners_create(request)


@csrf_exempt
def api_superadmin_edit_owner(request):
    """Allows Super Admin to update Shop Owner account details and shop information."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        name = data.get('name', '').strip()
        shop_name = data.get('shop_name', '').strip()
        phone = data.get('phone', '').strip()
        email = data.get('email', '').strip().lower()
        shop_code = data.get('shop_code', '').strip()
        address = data.get('address', '').strip()

        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return JsonResponse({'error': f"Shop Owner '{username}' not found"}, status=404)

        if phone and not re.match(r'^\d{10}$', phone):
            return JsonResponse({'error': 'Phone number must be exactly 10 digits.'}, status=400)

        if name:
            user.first_name = name
        if phone:
            user.phone_number = phone
        if email:
            user.email = email
        user.save()

        shop = Shop.objects.filter(owner=user).first()
        if shop:
            if shop_name:
                shop.name = shop_name
            if shop_code:
                shop.code = shop_code
            if phone:
                shop.phone = phone
            if email:
                shop.email = email
            if address:
                shop.address = address
            shop.save()

        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


def api_superadmin_reset_owner_password(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        new_password = data.get('new_password', '').strip()
        if not username or not new_password:
            return JsonResponse({'error': 'Username and new password required'}, status=400)
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return JsonResponse({'error': f"Shop Owner '{username}' not found"}, status=404)
        user.set_password(new_password)
        user.save()
        return JsonResponse({'success': True, 'username': username})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def api_superadmin_toggle_owner(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return JsonResponse({'error': 'Shop Owner not found'}, status=404)
        user.is_active = not user.is_active
        user.save()
        for s in user.owned_shops.all():
            s.status = Shop.Status.APPROVED if user.is_active else Shop.Status.SUSPENDED
            s.save()
        return JsonResponse({'success': True, 'is_active': user.is_active})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt
def api_superadmin_delete_owner(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        username = data.get('username', '').strip()
        user = User.objects.filter(username__iexact=username).first()
        if not user:
            return JsonResponse({'error': 'Shop Owner not found'}, status=404)
        user.is_active = False
        user.save()
        for s in user.owned_shops.all():
            s.status = Shop.Status.SUSPENDED
            s.save()
        return JsonResponse({'success': True})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@csrf_exempt


# ======================= POS: RAZORPAY PAYMENT GATEWAY INTEGRATION =======================

@csrf_exempt
def api_pos_create_razorpay_order(request):
    """
    Creates a Razorpay Payment Link and dynamic UPI QR Code locked to the exact cart amount.
    Returns: plink_id, short_url, qr_image_url (Base64 PNG), amount, bill_number, upi_intent.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        import razorpay
        import qrcode
        import io
        import base64

        data = json.loads(request.body)
        raw_amount = data.get('amount', 0)
        amount = round(float(raw_amount), 2)
        if amount <= 0:
            return JsonResponse({'error': 'Payable amount must be greater than zero.'}, status=400)

        shop_code = data.get('shop_code') or data.get('shop_id')
        shop = Shop.objects.filter(code__iexact=shop_code).first() if shop_code else Shop.objects.first()
        shop_name = shop.name if shop else "Smart Bazaar"
        upi_vpa = (shop.upi_vpa if shop and shop.upi_vpa else "smartbazaar@okaxis")

        customer_id = data.get('customer_id')
        customer = CustomerProfile.objects.filter(id=customer_id).first() if customer_id else None
        cust_name = data.get('customer_name') or (getattr(customer, 'full_name', None) or getattr(customer, 'name', 'Store Customer') if customer else 'Store Customer')
        cust_email = data.get('customer_email') or (customer.email if customer else '')
        cust_phone = data.get('customer_phone') or (getattr(customer, 'phone_number', None) or getattr(customer, 'phone', '') if customer else '')

        bill_ref = f"SB-BILL-{secrets.randbelow(900000) + 100000}"
        amount_in_paise = int(round(amount * 100))

        key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_U1IjfckRmPbWFi')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'T28L7b9fe28nGXug9RnYGkXl')

        client = razorpay.Client(auth=(key_id, key_secret))

        # Create Razorpay Payment Link with exact locked amount
        plink_payload = {
            'amount': amount_in_paise,
            'currency': 'INR',
            'accept_partial': False,
            'description': f"{shop_name} - Tax Invoice #{bill_ref}",
            'customer': {
                'name': cust_name,
                'email': cust_email or 'customer@smartbazaar.com',
                'contact': cust_phone or '+919999999999'
            },
            'notify': {'sms': False, 'email': False},
            'reminder_enable': False
        }

        # Standard UPI Intent String (direct UPI apps: PhonePe, GPay, Paytm, BHIM)
        upi_intent = f"upi://pay?pa={upi_vpa}&pn={shop_name.replace(' ', '%20')}&am={amount:.2f}&cu=INR&tn={bill_ref}"

        try:
            plink = client.payment_link.create(plink_payload)
            short_url = plink.get('short_url')
            plink_id = plink.get('id')
            qr_target = short_url or upi_intent
        except Exception as rzp_err:
            print(f"Razorpay live API call notice: {rzp_err}. Using direct UPI QR mode.")
            plink_id = f"plink_test_{secrets.token_hex(6)}"
            short_url = f"https://rzp.io/i/{plink_id}"
            qr_target = upi_intent

        # Generate High-Resolution QR Code (encodes the Razorpay Payment Link or direct UPI string)
        qr = qrcode.QRCode(version=1, box_size=8, border=2)
        qr.add_data(qr_target)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0F5132", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format='PNG')
        qr_image_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode('utf-8')

        return JsonResponse({
            'success': True,
            'plink_id': plink_id,
            'short_url': short_url,
            'qr_image_url': qr_image_url,
            'amount': amount,
            'bill_number': bill_ref,
            'shop_name': shop_name,
            'upi_intent': upi_intent
        })
    except Exception as e:
        return JsonResponse({'error': f"Failed to initialize Razorpay payment: {str(e)}"}, status=400)


@csrf_exempt
def api_pos_check_razorpay_status(request):
    """
    Checks real-time payment status of a Razorpay Payment Link.
    Returns: is_paid: True/False, status, payment_id.
    """
    try:
        import razorpay

        plink_id = request.GET.get('plink_id') or request.POST.get('plink_id')
        simulate = request.GET.get('simulate') == 'true' or request.POST.get('simulate') == 'true'

        if simulate:
            return JsonResponse({
                'success': True,
                'is_paid': True,
                'status': 'paid',
                'payment_id': f"pay_sim_{secrets.token_hex(6)}",
                'amount_paid': 0.0,
                'message': 'Simulated Dev Mode Approval'
            })

        if not plink_id:
            return JsonResponse({'error': 'plink_id required'}, status=400)

        key_id = getattr(settings, 'RAZORPAY_KEY_ID', 'rzp_test_U1IjfckRmPbWFi')
        key_secret = getattr(settings, 'RAZORPAY_KEY_SECRET', 'T28L7b9fe28nGXug9RnYGkXl')
        client = razorpay.Client(auth=(key_id, key_secret))

        plink = client.payment_link.fetch(plink_id)
        status = plink.get('status')  # 'created', 'paid', 'partially_paid', etc.
        payments = plink.get('payments') or []
        payment_id = payments[0].get('payment_id') if payments else None

        if status == 'paid':
            amount_paid = float(plink.get('amount_paid', 0)) / 100.0
            return JsonResponse({
                'success': True,
                'is_paid': True,
                'status': 'paid',
                'payment_id': payment_id or f"pay_{secrets.token_hex(6)}",
                'amount_paid': amount_paid
            })
        else:
            return JsonResponse({
                'success': True,
                'is_paid': False,
                'status': status
            })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ======================= POS: WEB CHECKOUT API =======================

@csrf_exempt
def api_pos_web_checkout(request):
    """Persists a Web POS checkout sale, deducts inventory, and updates customer spend/points."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        data = json.loads(request.body)
        items = data.get('items', [])
        customer_id = data.get('customer_id')
        if not items:
            return JsonResponse({'error': 'Cart is empty'}, status=400)

        # Payment mode & transaction ID
        chosen_pay_mode = (data.get('payment_method') or 'CASH').upper()
        if any(k in chosen_pay_mode for k in ('ONLINE', 'UPI', 'RAZORPAY')):
            sale_pay_method = Sale.PaymentMethod.UPI
            pay_method_label = "Razorpay Online (UPI)"
        else:
            sale_pay_method = Sale.PaymentMethod.CASH
            pay_method_label = "Cash"

        txn_id = data.get('transaction_id') or data.get('payment_id') or f"TXN-{secrets.randbelow(900000) + 100000}"

        # Identify cashier if provided
        cashier_key = data.get('cashier_id') or data.get('cashier_username') or data.get('cashier_name')
        worker = None
        if cashier_key:
            worker = User.objects.filter(username__iexact=cashier_key).first()
            if not worker and '@' in cashier_key:
                worker = User.objects.filter(email__iexact=cashier_key).first()
        if not worker:
            worker = User.objects.filter(role=User.Role.WORKER, is_active=True).first() or User.objects.filter(is_active=True).first()

        # Identify shop if provided
        shop_key = data.get('shop_code') or data.get('shop_id')
        shop = None
        if shop_key:
            shop = Shop.objects.filter(code__iexact=shop_key).first()
            if not shop:
                try:
                    shop = Shop.objects.filter(id=shop_key).first()
                except Exception:
                    pass
        if not shop and worker:
            m = ShopMembership.objects.filter(user=worker).first()
            if m and m.shop:
                shop = m.shop
        if not shop:
            shop = Shop.objects.first()
        customer = CustomerProfile.objects.filter(id=customer_id).first() if customer_id else None

        with transaction.atomic():
            subtotal = Decimal('0.00')
            tax_total = Decimal('0.00')
            resolved = []
            updated_stocks = {}

            for it in items:
                pid = it.get('product_id') or it.get('id')
                qty = Decimal(str(it.get('quantity') or it.get('qty') or 1))
                prod = Product.objects.select_for_update().get(id=pid)
                inv = Inventory.objects.select_for_update().filter(product=prod, shop=shop).first()
                line_sub = (prod.selling_price * qty).quantize(Decimal('0.01'))
                line_tax = (line_sub * (prod.tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'))
                subtotal += line_sub
                tax_total += line_tax
                resolved.append((prod, inv, qty, line_sub, line_tax))

            final_total = (subtotal + tax_total).quantize(Decimal('0.01'))
            bill_number = data.get('bill_number') or f"SB-BILL-{secrets.randbelow(900000) + 100000}"

            sale = Sale.objects.create(
                shop=shop,
                worker=worker,
                customer=customer,
                bill_number=bill_number,
                is_guest=customer is None,
                subtotal=subtotal,
                tax_amount=tax_total,
                final_total=final_total,
                payment_method=sale_pay_method,
                payment_status=Sale.PaymentStatus.COMPLETED,
                idempotency_key=f"webpos-{secrets.token_hex(8)}"
            )

            for prod, inv, qty, line_sub, line_tax in resolved:
                barcode = prod.barcodes.first().barcode if prod.barcodes.exists() else prod.sku
                SaleItem.objects.create(
                    sale=sale,
                    product=prod,
                    product_name=prod.name,
                    barcode=barcode,
                    quantity=qty,
                    unit_price=prod.selling_price,
                    tax_rate=prod.tax_rate,
                    tax_amount=line_tax,
                    total_price=line_sub + line_tax,
                )
                if inv:
                    inv.current_stock = max(Decimal('0.00'), inv.current_stock - qty)
                    inv.save()
                    updated_stocks[str(prod.id)] = float(inv.current_stock)
                    StockTransaction.objects.create(
                        shop=shop,
                        product=prod,
                        tx_type=StockTransaction.TxType.SALE,
                        quantity=-qty,
                        balance_after=inv.current_stock,
                        reference_id=bill_number,
                        performed_by=worker
                    )

            Payment.objects.create(
                sale=sale,
                amount=final_total,
                payment_method=sale_pay_method,
                transaction_id=txn_id,
                is_success=True
            )
            Invoice.objects.create(
                sale=sale,
                invoice_number=f"INV-{bill_number}",
                qr_data=f"upi://pay?pa={shop.upi_vpa or 'smartbazaar@okaxis'}&pn={shop.name}&am={final_total}&cu=INR&tn={bill_number}",
                sent_to_email=customer.email if customer else ''
            )

            if customer:
                customer.total_spent = Decimal(str(customer.total_spent)) + final_total
                customer.visit_count += 1
                customer.reward_points += int(final_total // 100)
                if not customer.registered_at_shop and shop:
                    customer.registered_at_shop = shop
                customer.save()
                if shop:
                    try:
                        from apps.customers.models import CustomerShopAccount
                        csa, _ = CustomerShopAccount.objects.using('default').get_or_create(customer=customer, shop=shop)
                        csa.shop_total_spent = Decimal(str(csa.shop_total_spent)) + final_total
                        csa.visit_count += 1
                        csa.last_visit = timezone.now()
                        csa.save(using='default')
                    except Exception:
                        pass

        # Determine store personnel & watermark logo details
        shop_name = shop.name if shop else "Smart Bazaar"
        shop_code = shop.code if shop else "SB-SHOP-001"
        shop_owner_name = "Store Owner"
        if shop and shop.owner:
            shop_owner_name = shop.owner.get_full_name() or shop.owner.username
        shop_address = shop.address if shop else "Station Road, Kolkata - 700001"
        shop_phone = shop.phone if shop else "+91 96922 76657"

        cashier_name = (worker.get_full_name() if (worker and worker.get_full_name()) else (worker.username if worker else (data.get('cashier_name') or "Cashier")))
        cashier_id = (worker.username if worker else (data.get('cashier_id') or "STAFF-01"))

        logo_path = None
        if shop and shop.logo:
            try:
                if os.path.exists(shop.logo.path):
                    logo_path = shop.logo.path
            except Exception:
                pass

        raw_cust_dict = data.get('customer') if isinstance(data.get('customer'), dict) else {}
        email_recipient = (customer.email if customer and customer.email else (data.get('customer_email') or raw_cust_dict.get('email') or '')).strip().lower()
        email_sent = False
        email_error = None

        # Generate PDF receipt with watermark and dispatch via Gmail API to customer
        if email_recipient:
            try:
                from apps.core.receipt_pdf import generate_receipt_pdf
                from apps.core.email_service import EmailService

                items_for_receipt = []
                for prod, inv, qty, line_sub, line_tax in resolved:
                    barcode = prod.barcodes.first().barcode if prod.barcodes.exists() else prod.sku
                    items_for_receipt.append({
                        'name': prod.name,
                        'barcode': barcode,
                        'qty': float(qty),
                        'price': float(prod.selling_price),
                        'total': float(line_sub + line_tax)
                    })

                now_str = timezone.now().strftime("%d %b %Y, %I:%M %p")
                customer_code = (getattr(customer, 'customer_code', None) or (f"SB-CUST-{customer.id}" if customer else (data.get('customer_code') or raw_cust_dict.get('code') or "SB-GUEST")))
                cust_full_name = (getattr(customer, 'full_name', None) or getattr(customer, 'name', None) or data.get('customer_name') or raw_cust_dict.get('name') or 'Valued Customer')
                cust_phone_num = (getattr(customer, 'phone_number', None) or getattr(customer, 'phone', None) or data.get('customer_phone') or raw_cust_dict.get('phone') or 'N/A')

                pdf_bytes = generate_receipt_pdf(
                    shop_name=shop_name,
                    shop_code=shop_code,
                    shop_owner_name=shop_owner_name,
                    shop_address=shop_address,
                    shop_phone=shop_phone,
                    cashier_name=cashier_name,
                    cashier_id=cashier_id,
                    customer_name=cust_full_name,
                    customer_phone=cust_phone_num,
                    customer_code=customer_code,
                    customer_email=email_recipient,
                    bill_number=bill_number,
                    items=items_for_receipt,
                    subtotal=float(subtotal),
                    tax_amount=float(tax_total),
                    final_total=float(final_total),
                    payment_method=pay_method_label,
                    created_at_str=now_str,
                    logo_path=logo_path
                )

                email_res = EmailService.sendCustomerBillReceiptEmail(
                    recipient_email=email_recipient,
                    customer_name=cust_full_name,
                    customer_phone=cust_phone_num,
                    customer_code=customer_code,
                    shop_name=shop_name,
                    shop_code=shop_code,
                    shop_owner_name=shop_owner_name,
                    shop_address=shop_address,
                    shop_phone=shop_phone,
                    cashier_name=cashier_name,
                    cashier_id=cashier_id,
                    bill_number=bill_number,
                    items=items_for_receipt,
                    subtotal=float(subtotal),
                    tax_amount=float(tax_total),
                    final_total=float(final_total),
                    payment_method=pay_method_label,
                    created_at_str=now_str,
                    pdf_bytes=pdf_bytes,
                    shop_id=str(shop.id) if shop else None
                )
                email_sent = email_res.get('success', False)
                if not email_sent:
                    email_error = email_res.get('error')
            except Exception as em_err:
                email_error = str(em_err)
                print(f"[CHECKOUT EMAIL / PDF ERROR]: {em_err}")

        alerts = [
            {
                'product_id': str(n.product_id),
                'product_name': n.product.name,
                'current_stock': float(n.current_stock),
                'threshold': LOW_STOCK_THRESHOLD,
                'severity': n.severity,
                'message': n.message,
            }
            for n in StockNotification.objects.filter(shop=shop, is_resolved=False).select_related('product')
        ]

        return JsonResponse({
            'success': True,
            'bill_number': bill_number,
            'final_total': float(final_total),
            'payment_method': pay_method_label,
            'transaction_id': txn_id,
            'updated_stocks': updated_stocks,
            'low_stock_alerts': alerts,
            'email_sent': email_sent,
            'email_recipient': email_recipient,
            'email_error': email_error,
            'owner_name': shop_owner_name,
            'cashier_name': cashier_name,
            'cashier_id': cashier_id,
            'shop_logo_url': shop.logo.url if (shop and shop.logo) else None
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)



@csrf_exempt


# ======================= PAGE VIEW ENDPOINTS =======================


def download_apk(request, variant):
    base_dir = Path(settings.BASE_DIR).parent
    if variant == 'release':
        apk_path = base_dir / 'mobile' / 'build' / 'app' / 'outputs' / 'flutter-apk' / 'app-release.apk'
        filename = 'SmartBazaar-Release.apk'
    elif variant == 'debug':
        apk_path = base_dir / 'mobile' / 'build' / 'app' / 'outputs' / 'flutter-apk' / 'app-debug.apk'
        filename = 'SmartBazaar-Debug.apk'
    else:
        raise Http404("Invalid APK variant")

    if not apk_path.exists():
        raise Http404("APK file not found on server.")

    response = FileResponse(open(apk_path, 'rb'), content_type='application/vnd.android.package-archive')
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


def pwa_manifest(request):
    """
    Serves the Progressive Web App manifest for Android & mobile installability.
    """
    manifest_data = {
        "name": "Smart Bazaar — Supermarket POS & Management",
        "short_name": "SmartBazaar",
        "description": "Multi-Branch Supermarket Management, Mobile POS, Inventory, and Thermal Receipt System",
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": "#F8FAFC",
        "theme_color": "#0F5132",
        "categories": ["business", "shopping", "productivity"],
        "icons": [
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 192 192'%3E%3Crect width='192' height='192' rx='44' fill='%230F5132'/%3E%3Ctext x='96' y='128' font-size='100' text-anchor='middle'%3E🛍️%3C/text%3E%3C/svg%3E",
                "sizes": "192x192",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            },
            {
                "src": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 512 512'%3E%3Crect width='512' height='512' rx='116' fill='%230F5132'/%3E%3Ctext x='256' y='340' font-size='270' text-anchor='middle'%3E🛍️%3C/text%3E%3C/svg%3E",
                "sizes": "512x512",
                "type": "image/svg+xml",
                "purpose": "any maskable"
            }
        ]
    }
    return JsonResponse(manifest_data, content_type='application/manifest+json')


def pwa_service_worker(request):
    """
    Serves the modern PWA Service Worker for offline resilience and fast mobile caching.
    """
    sw_script = """// Smart Bazaar PWA Service Worker (Mobile-First)
const CACHE_NAME = 'smart-bazaar-green-v1';
const SHELL_URLS = [
    '/',
    '/manifest.json'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(SHELL_URLS).catch(() => {});
        })
    );
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
            );
        })
    );
    self.clients.claim();
});

self.addEventListener('fetch', (event) => {
    if (event.request.method !== 'GET') return;
    const url = new URL(event.request.url);
    
    // Pass API and checkout requests straight through
    if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/download/')) {
        return;
    }

    if (event.request.mode === 'navigate') {
        event.respondWith(
            fetch(event.request).catch(() => {
                return caches.match('/') || new Response(
                    '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>Smart Bazaar Offline</title></head><body style="margin:0;padding:40px 20px;font-family:sans-serif;background:#F8FAFC;text-align:center;color:#0F5132;"><div style="font-size:4rem;margin-bottom:16px;">🛍️</div><h2 style="margin:0 0 8px;">Smart Bazaar Offline</h2><p style="color:#64748B;margin:0 0 24px;">You appear to be offline. Reconnect to sync with your store database.</p><button onclick="location.reload()" style="background:#0F5132;color:white;border:none;padding:12px 28px;border-radius:12px;font-weight:700;font-size:1rem;cursor:pointer;">Retry Connection</button></body></html>',
                    { headers: { 'Content-Type': 'text/html' } }
                );
            })
        );
        return;
    }

    event.respondWith(
        caches.match(event.request).then((cached) => {
            const networked = fetch(event.request).then((resp) => {
                if (resp && resp.status === 200 && resp.type === 'basic') {
                    const copy = resp.clone();
                    caches.open(CACHE_NAME).then((c) => c.put(event.request, copy));
                }
                return resp;
            }).catch(() => cached);
            return cached || networked;
        })
    );
});
"""
    return HttpResponse(sw_script, content_type='application/javascript')



def barcode_catalog_page(request):
    """
    Renders a dedicated, printable Barcode Label Catalog of all 200+ products
    with their exact 1D barcode images matching the user's specification.
    """
    products = []
    for p in Product.objects.all().select_related('inventory', 'category').order_by('name'):
        barcode = p.barcodes.first().barcode if p.barcodes.exists() else p.sku
        stock = getattr(p, 'inventory', None)
        current_stock = float(stock.current_stock) if stock else 0.0
        products.append({
            'id': str(p.id),
            'name': p.name,
            'barcode': barcode or p.sku,
            'selling_price': float(p.selling_price),
            'mrp': float(p.mrp),
            'stock': current_stock,
            'unit': p.unit,
            'category': p.category.name if p.category else 'General',
        })

    products_json = json.dumps(products)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Smart Bazaar — 200 Product Barcode Catalog & Label Sheet</title>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
    <style>
        :root {{
            --primary: #0F5132;
            --secondary: #15803D;
            --success: #16A34A;
            --bg: #F8FAFC;
            --card: #FFFFFF;
            --border: #E2E8F0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: 'Plus Jakarta Sans', sans-serif;
            background: var(--bg);
            color: #0F172A;
            padding-bottom: 50px;
        }}
        .header-bar {{
            background: linear-gradient(135deg, #0F5132 0%, #451778 100%);
            color: white;
            padding: 1.25rem 2rem;
            position: sticky;
            top: 0;
            z-index: 100;
            box-shadow: 0 4px 20px rgba(15, 81, 50, 0.25);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .btn {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: white;
            color: var(--primary);
            font-weight: 700;
            font-size: 0.88rem;
            padding: 8px 16px;
            border-radius: 8px;
            border: none;
            cursor: pointer;
            text-decoration: none;
            transition: all 0.2s;
        }}
        .btn:hover {{ background: #DCFCE7; transform: translateY(-1px); }}
        .btn-primary {{
            background: #22C55E;
            color: white;
        }}
        .btn-primary:hover {{ background: #15803D; }}
        .btn-outline {{
            background: transparent;
            color: white;
            border: 1.5px solid rgba(255,255,255,0.4);
        }}
        .btn-outline:hover {{ background: rgba(255,255,255,0.15); }}
        .search-box {{
            padding: 10px 16px;
            border-radius: 8px;
            border: none;
            font-size: 0.95rem;
            width: 320px;
            outline: none;
        }}
        .container {{
            max-width: 1350px;
            margin: 24px auto;
            padding: 0 1.5rem;
        }}
        .info-card {{
            background: white;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 24px;
            border: 1px solid var(--border);
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 12px;
        }}
        .labels-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(290px, 1fr));
            gap: 18px;
        }}
        .label-card {{
            background: white;
            border: 1.5px solid var(--border);
            border-radius: 12px;
            padding: 16px;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            box-shadow: 0 2px 10px rgba(0,0,0,0.03);
            position: relative;
            transition: transform 0.15s, box-shadow 0.15s;
        }}
        .label-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(95,37,159,0.1);
            border-color: var(--primary);
        }}
        .label-store {{
            font-size: 0.72rem;
            color: var(--primary);
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .label-title {{
            font-size: 0.95rem;
            font-weight: 700;
            color: #1E293B;
            margin-bottom: 6px;
            min-height: 42px;
            line-height: 1.35;
        }}
        .label-prices {{
            display: flex;
            justify-content: space-between;
            align-items: baseline;
            margin-bottom: 12px;
            padding-bottom: 8px;
            border-bottom: 1px dashed var(--border);
        }}
        .selling-price {{
            font-size: 1.25rem;
            font-weight: 800;
            color: var(--success);
        }}
        .mrp-price {{
            font-size: 0.85rem;
            color: #94A3B8;
            text-decoration: line-through;
        }}
        .barcode-img-box {{
            background: #FFFFFF;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            padding: 10px 6px;
            text-align: center;
            margin-bottom: 10px;
        }}
        .barcode-img {{
            max-width: 100%;
            height: 72px;
            object-fit: contain;
            display: block;
            margin: 0 auto;
        }}
        .barcode-num {{
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.85rem;
            font-weight: 700;
            letter-spacing: 1.5px;
            color: #334155;
            margin-top: 4px;
            display: block;
        }}
        .label-actions {{
            display: flex;
            gap: 6px;
            margin-top: 6px;
        }}
        .label-btn {{
            flex: 1;
            padding: 6px 8px;
            font-size: 0.75rem;
            font-weight: 700;
            border-radius: 6px;
            border: 1px solid var(--border);
            background: #F8FAFC;
            color: #334155;
            cursor: pointer;
            text-align: center;
            text-decoration: none;
            transition: 0.15s;
        }}
        .label-btn:hover {{
            background: #DCFCE7;
            color: var(--primary);
            border-color: var(--primary);
        }}
        .label-btn-pos {{
            background: var(--primary);
            color: white;
            border: none;
        }}
        .label-btn-pos:hover {{
            background: #451778;
            color: white;
        }}

        @media (max-width: 768px) {{
            .header-bar {{ padding: 1rem; flex-direction: column; align-items: stretch; gap: 10px; }}
            .header-bar > div {{ flex-direction: column; align-items: stretch !important; width: 100%; }}
            .search-box {{ width: 100%; }}
            .container {{ padding: 0 12px; margin: 16px auto; }}
            .labels-grid {{ grid-template-columns: 1fr; gap: 14px; }}
            .info-card {{ flex-direction: column; align-items: flex-start; }}
        }}
        @media (min-width: 480px) and (max-width: 768px) {{
            .labels-grid {{ grid-template-columns: repeat(2, 1fr); gap: 12px; }}
        }}

        @media print {{
            .no-print {{ display: none !important; }}
            body {{ background: white; padding: 0; }}
            .container {{ max-width: 100%; margin: 0; padding: 0; }}
            .labels-grid {{
                grid-template-columns: repeat(3, 1fr);
                gap: 12px;
            }}
            .label-card {{
                break-inside: avoid;
                page-break-inside: avoid;
                border: 1px solid #000;
                box-shadow: none;
                padding: 10px;
            }}
            .label-actions {{ display: none !important; }}
            .barcode-img {{ height: 60px; }}
        }}
    </style>
</head>
<body>
    <div class="header-bar no-print">
        <div style="display: flex; align-items: center; gap: 12px;">
            <a href="/" class="btn btn-outline">&larr; Back to Admin & POS</a>
            <h1 style="font-size: 1.25rem; font-weight: 800; letter-spacing: -0.5px;">
                🛍️ Smart Bazaar &bull; 200 Product Barcode Catalog
            </h1>
        </div>
        <div style="display: flex; align-items: center; gap: 10px;">
            <input type="text" id="catalogSearch" class="search-box" placeholder="🔍 Search product or barcode..." oninput="filterCatalog()">
            <button onclick="window.print()" class="btn btn-primary">🖨️ Print Label Stickers</button>
        </div>
    </div>

    <div class="container">
        <div class="info-card no-print">
            <div>
                <strong style="font-size: 1rem; color: var(--primary);">📷 High-Resolution 1D Barcode Images</strong>
                <p style="font-size: 0.85rem; color: #64748B; margin-top: 4px;">
                    Every product has its unique 1D barcode image generated. Point your phone camera, Android APK scanner, or USB barcode reader at any barcode below to automatically decode and add the product with price and stock to the cart!
                </p>
            </div>
            <div style="font-weight: 700; font-size: 0.95rem; color: var(--success); background: #DCFCE7; padding: 6px 14px; border-radius: 999px;">
                ✓ <span id="labelCountBadge">{len(products)}</span> Scannable Barcode Labels Loaded
            </div>
        </div>

        <div id="labelsGrid" class="labels-grid"></div>
    </div>

    <script>
        const catalogProducts = {products_json};

        function renderCatalog(list = null) {{
            const items = list || catalogProducts;
            const grid = document.getElementById('labelsGrid');
            document.getElementById('labelCountBadge').innerText = items.length;
            grid.innerHTML = '';

            if (items.length === 0) {{
                grid.innerHTML = '<div style="grid-column: 1/-1; text-align: center; padding: 40px; color: #64748B; font-weight: 600;">No products match your search.</div>';
                return;
            }}

            items.forEach(p => {{
                grid.innerHTML += `
                    <div class="label-card">
                        <div>
                            <div class="label-store">Smart Bazaar &bull; ${{p.category}}</div>
                            <div class="label-title">${{p.name}}</div>
                            <div class="label-prices">
                                <div>
                                    <span class="selling-price">₹${{p.selling_price.toFixed(2)}}</span>
                                    <span style="font-size: 0.78rem; color: #64748B;">/ ${{p.unit}}</span>
                                </div>
                                <span class="mrp-price">MRP ₹${{p.mrp.toFixed(2)}}</span>
                            </div>
                        </div>

                        <div>
                            <!-- EXACT 1D BARCODE IMAGE -->
                            <div class="barcode-img-box">
                                <img src="/api/products/barcode-image/${{p.barcode}}/?text=0" class="barcode-img" alt="Barcode ${{p.barcode}}">
                                <span class="barcode-num">${{p.barcode}}</span>
                            </div>

                            <div class="label-actions no-print">
                                <button onclick="quickTestScan('${{p.barcode}}', '${{encodeURIComponent(p.name)}}')" class="label-btn label-btn-pos">
                                    ⚡ Scan to POS
                                </button>
                                <a href="/api/products/barcode-image/${{p.barcode}}/?text=0&download=1" class="label-btn">
                                    ⬇️ PNG
                                </a>
                            </div>
                        </div>
                    </div>
                `;
            }});
        }}

        function filterCatalog() {{
            const q = document.getElementById('catalogSearch').value.toLowerCase().trim();
            if (!q) {{
                renderCatalog();
                return;
            }}
            const filtered = catalogProducts.filter(p => 
                p.name.toLowerCase().includes(q) || 
                p.barcode.toLowerCase().includes(q) || 
                p.category.toLowerCase().includes(q)
            );
            renderCatalog(filtered);
        }}

        function quickTestScan(barcode, prodName) {{
            // Store barcode in sessionStorage for automatic scan when POS opens
            sessionStorage.setItem('autoScanBarcode', barcode);
            window.location.href = '/?autoScan=' + barcode;
        }}

        renderCatalog();
    </script>
</body>
</html>
"""
    return HttpResponse(html)