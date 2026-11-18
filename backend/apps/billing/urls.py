from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.billing.views import SaleViewSet, CreateSaleView, ThermalReceiptView

router = DefaultRouter()
router.register(r'', SaleViewSet, basename='sales')

urlpatterns = [
    path('checkout/', CreateSaleView.as_view(), name='sale-checkout'),
    path('<uuid:sale_id>/receipt/', ThermalReceiptView.as_view(), name='sale-receipt'),
    path('', include(router.urls)),
]

