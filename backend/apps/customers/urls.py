from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.customers.views import OfferViewSet, CustomerSummaryView, CustomerWalletView

router = DefaultRouter()
router.register(r'offers', OfferViewSet, basename='offers')

urlpatterns = [
    path('summary/', CustomerSummaryView.as_view(), name='customer-summary'),
    path('wallet/', CustomerWalletView.as_view(), name='customer-wallet'),
    path('', include(router.urls)),
]

