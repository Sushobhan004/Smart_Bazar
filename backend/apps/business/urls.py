from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.business.views import ExpenseViewSet, CashShiftViewSet, BusinessReportsView

router = DefaultRouter()
router.register(r'expenses', ExpenseViewSet, basename='expenses')
router.register(r'shifts', CashShiftViewSet, basename='shifts')

urlpatterns = [
    path('reports/', BusinessReportsView.as_view(), name='business-reports'),
    path('', include(router.urls)),
]

