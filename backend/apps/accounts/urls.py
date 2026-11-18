from django.urls import path
from apps.accounts.views import (
    SendOTPView, VerifyOTPView, StaffLoginView,
    CustomerSearchView, WorkerAssistedRegisterView, CustomerMeView
)
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('send-otp/', SendOTPView.as_view(), name='send-otp'),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('staff-login/', StaffLoginView.as_view(), name='staff-login'),
    path('staff/login/', StaffLoginView.as_view(), name='staff-login-slash'),
    path('refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('customers/search/', CustomerSearchView.as_view(), name='customer-search'),
    path('customers/register/', WorkerAssistedRegisterView.as_view(), name='customer-worker-register'),
    path('customers/me/', CustomerMeView.as_view(), name='customer-me'),
]

