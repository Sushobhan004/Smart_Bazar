from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.shops.views import ShopViewSet, ShopMembershipViewSet

router = DefaultRouter()
router.register(r'memberships', ShopMembershipViewSet, basename='shop-memberships')
router.register(r'', ShopViewSet, basename='shops')

urlpatterns = [
    path('', include(router.urls)),
]

