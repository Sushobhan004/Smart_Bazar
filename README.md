# Smart Bazaar — Production Android Retail POS, Inventory & Customer Management

A commercial-grade multi-tenant retail POS ecosystem featuring a PhonePe-inspired Flutter Android application, Django REST Framework backend with PostgreSQL/SQLite, offline Drift synchronization, passwordless Gmail OTP customer authentication, worker-assisted registration, barcode/QR scanning, inventory ledger, and loyalty rewards engine.

---

## Architecture Overview

- **Mobile Client**: Flutter 3.47 + Dart 3.13, PhonePe-inspired fintech design system (`#5F259F` primary), 5-tab bottom navigation with central elevated QR scanner, live retail POS billing cart, Bluetooth thermal printer support.
- **Backend API**: Python 3.12 + Django 6.0 + Django REST Framework + SimpleJWT.
- **Tenant Isolation**: Separate store namespaces, inventories, prices, cash shifts, and staff access controls.
- **Customer Identity**: STRICT Passwordless Gmail OTP authentication ONLY. Worker-assisted customer registration verifies via Gmail OTP before bill completion.

---

## Default Demonstration Accounts

| Role | Username / Identifier | Password / Auth | Purpose |
|---|---|---|---|
| **Super Admin** | `admin` | `Admin@123` | Platform oversight, shop approvals, global audit logs |
| **Shop Owner** | `owner_grocery` | `Owner@123` | Store inventory, reports, revenue analytics, cash closing |
| **Cashier / Worker** | `cashier_arun` | `Worker@123` | Retail POS billing, customer lookup, barcode scanning |
| **Customer** | `rahul.customer@gmail.com` | **Passwordless Gmail OTP** | Self-service bills, rewards wallet, store directory |

---

## Running the Ecosystem

### 1. Backend REST API
```bash
cd backend
python manage.py migrate
python seed_data.py
python manage.py runserver 0.0.0.0:8000
```

### 2. Run Backend Test Suite
```bash
cd backend
python manage.py test apps.accounts apps.billing
```

### 3. Flutter Android App
```bash
cd mobile
flutter run
# Or build APK:
flutter build apk --debug
flutter build apk --release
```
Artifact Output: `mobile/build/app/outputs/flutter-apk/app-debug.apk`

