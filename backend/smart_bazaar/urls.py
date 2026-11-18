from django.contrib import admin
from django.urls import path, include
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static
from apps.core.views import (
    landing_page, 
    download_apk,
    pwa_manifest,
    pwa_service_worker,
    barcode_catalog_page,
    api_admin_add_product,
    api_admin_delete_product,
    api_admin_update_product,
    api_admin_send_worker_otp,
    api_admin_add_worker,
    api_admin_reset_worker_password,
    api_admin_toggle_worker,
    api_admin_delete_worker,
    api_admin_upload_shop_logo,
    api_admin_update_shop_profile,
    api_superadmin_send_owner_otp,
    api_superadmin_add_owner,
    api_superadmin_edit_owner,
    api_superadmin_reset_owner_password,
    api_superadmin_toggle_owner,
    api_superadmin_delete_owner,
    api_pos_web_checkout,
    api_pos_create_razorpay_order,
    api_pos_check_razorpay_status,
)
from apps.core.workflow_views import (
    api_superadmin_owners_send_otp,
    api_superadmin_owners_verify_otp,
    api_superadmin_owners_create,
    api_shop_employees_send_otp,
    api_shop_employees_verify_otp,
    api_shop_employees_create,
    api_shop_customers_send_otp,
    api_shop_customers_verify_otp,
    api_shop_customers_create,
    api_shop_customers_list,
    api_email_send_test,
)

urlpatterns = [
    path('', landing_page, name='landing_page'),
    path('manifest.json', pwa_manifest, name='pwa_manifest'),
    path('sw.js', pwa_service_worker, name='pwa_service_worker'),
    path('barcodes/', barcode_catalog_page, name='barcode_catalog_page'),
    path('download/<str:variant>/', download_apk, name='download_apk'),
    
    # POS Web Checkout & Razorpay Payment Integration
    path('api/pos/checkout/', api_pos_web_checkout, name='api_pos_web_checkout'),
    path('api/pos/create-payment-order/', api_pos_create_razorpay_order, name='api_pos_create_razorpay_order'),
    path('api/pos/check-payment-status/', api_pos_check_razorpay_status, name='api_pos_check_razorpay_status'),

    # Super Admin Operations API (Shop Owners & Gmail OTP)
    path('api/super-admin/owners/send-otp', api_superadmin_owners_send_otp, name='api_super_admin_owners_send_otp'),
    path('api/super-admin/owners/send-otp/', api_superadmin_owners_send_otp),
    path('api/superadmin/owners/send-otp/', api_superadmin_owners_send_otp, name='api_superadmin_send_owner_otp'),
    path('api/super-admin/owners/verify-otp', api_superadmin_owners_verify_otp, name='api_super_admin_owners_verify_otp'),
    path('api/super-admin/owners/verify-otp/', api_superadmin_owners_verify_otp),
    path('api/superadmin/owners/verify-otp/', api_superadmin_owners_verify_otp),
    path('api/super-admin/owners/create', api_superadmin_owners_create, name='api_super_admin_owners_create'),
    path('api/super-admin/owners/create/', api_superadmin_owners_create),
    path('api/superadmin/owners/create/', api_superadmin_owners_create, name='api_superadmin_add_owner'),
    path('api/superadmin/owners/edit/', api_superadmin_edit_owner, name='api_superadmin_edit_owner'),
    path('api/superadmin/owners/reset-password/', api_superadmin_reset_owner_password, name='api_superadmin_reset_owner_password'),
    path('api/superadmin/owners/toggle-status/', api_superadmin_toggle_owner, name='api_superadmin_toggle_owner'),
    path('api/superadmin/owners/delete/', api_superadmin_delete_owner, name='api_superadmin_delete_owner'),

    # Shop Level Employee Management API (with Gmail API OTP)
    path('api/shop/employees/send-otp', api_shop_employees_send_otp, name='api_shop_employees_send_otp'),
    path('api/shop/employees/send-otp/', api_shop_employees_send_otp),
    path('api/admin/workers/send-otp/', api_shop_employees_send_otp, name='api_admin_send_worker_otp'),
    path('api/shop/employees/verify-otp', api_shop_employees_verify_otp, name='api_shop_employees_verify_otp'),
    path('api/shop/employees/verify-otp/', api_shop_employees_verify_otp),
    path('api/admin/workers/verify-otp/', api_shop_employees_verify_otp),
    path('api/shop/employees/create', api_shop_employees_create, name='api_shop_employees_create'),
    path('api/shop/employees/create/', api_shop_employees_create),
    path('api/admin/workers/create/', api_shop_employees_create, name='api_admin_add_worker'),
    path('api/admin/workers/reset-password/', api_admin_reset_worker_password, name='api_admin_reset_worker_password'),
    path('api/admin/workers/toggle-access/', api_admin_toggle_worker, name='api_admin_toggle_worker'),
    path('api/admin/workers/delete/', api_admin_delete_worker, name='api_admin_delete_worker'),

    # Customer Registration API (with Gmail API OTP)
    path('api/shop/customers/send-otp', api_shop_customers_send_otp, name='api_shop_customers_send_otp'),
    path('api/shop/customers/send-otp/', api_shop_customers_send_otp),
    path('api/customers/send-otp/', api_shop_customers_send_otp),
    path('api/pos/customers/send-otp/', api_shop_customers_send_otp),
    path('api/shop/customers/verify-otp', api_shop_customers_verify_otp, name='api_shop_customers_verify_otp'),
    path('api/shop/customers/verify-otp/', api_shop_customers_verify_otp),
    path('api/customers/verify-otp/', api_shop_customers_verify_otp),
    path('api/pos/customers/verify-otp/', api_shop_customers_verify_otp),
    path('api/shop/customers/create', api_shop_customers_create, name='api_shop_customers_create'),
    path('api/shop/customers/create/', api_shop_customers_create),
    path('api/pos/customers/create/', api_shop_customers_create),
    path('api/shop/customers/', api_shop_customers_list, name='api_shop_customers_list'),
    path('api/shop/customers/list/', api_shop_customers_list),

    # Gmail API Connectivity & Health Test
    path('api/email/send-test', api_email_send_test, name='api_email_send_test'),
    path('api/email/send-test/', api_email_send_test),

    # Admin Panel Operations API (Store Level)
    path('api/admin/products/add/', api_admin_add_product, name='api_admin_add_product'),
    path('api/admin/products/delete/', api_admin_delete_product, name='api_admin_delete_product'),
    path('api/admin/products/update/', api_admin_update_product, name='api_admin_update_product'),
    path('api/admin/shop/upload-logo/', api_admin_upload_shop_logo, name='api_admin_upload_shop_logo'),
    path('api/admin/shop/update-profile/', api_admin_update_shop_profile, name='api_admin_update_shop_profile'),

    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/customers/', include('apps.customers.urls')),
    path('api/shops/', include('apps.shops.urls')),
    path('api/products/', include('apps.products.urls')),
    path('api/inventory/', include('apps.inventory.urls')),
    path('api/sales/', include('apps.billing.urls')),
    path('api/procurement/', include('apps.suppliers.urls')),
    path('api/business/', include('apps.business.urls')),
    path('api/sync/', include('apps.sync.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
