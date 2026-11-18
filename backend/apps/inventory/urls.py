from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.inventory.views import (
    InventoryViewSet,
    StockAdjustmentView,
    StockTransactionListView,
    LowStockAlertsView,
    AcknowledgeLowStockAlertsView,
)

router = DefaultRouter()
router.register(r'', InventoryViewSet, basename='inventory')

urlpatterns = [
    path('adjust/', StockAdjustmentView.as_view(), name='stock-adjust'),
    path('transactions/', StockTransactionListView.as_view(), name='stock-transactions'),
    path('low-stock-alerts/', LowStockAlertsView.as_view(), name='low-stock-alerts'),
    path('low-stock-alerts/acknowledge/', AcknowledgeLowStockAlertsView.as_view(), name='low-stock-alerts-ack'),
    path('', include(router.urls)),
]

