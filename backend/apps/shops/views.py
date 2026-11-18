import secrets
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.shops.models import Shop, ShopMembership
from apps.shops.serializers import ShopSerializer, ShopMembershipSerializer
from apps.accounts.models import User

class IsSuperAdminOrReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return bool(request.user and request.user.is_authenticated and request.user.is_super_admin())

class ShopViewSet(viewsets.ModelViewSet):
    serializer_class = ShopSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        if not user or not user.is_authenticated:
            return Shop.objects.filter(status=Shop.Status.APPROVED)
        if user.is_super_admin():
            return Shop.objects.all()
        if user.is_shop_owner():
            return Shop.objects.filter(owner=user)
        if user.is_worker():
            return Shop.objects.filter(memberships__user=user, memberships__is_active=True)
        # Customer view: all approved active shops
        return Shop.objects.filter(status=Shop.Status.APPROVED)

    def perform_create(self, serializer):
        user = self.request.user
        code = f"SB-SHOP-{secrets.randbelow(9000) + 1000}"
        serializer.save(owner=user, code=code)

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def approve(self, request, pk=None):
        if not request.user.is_super_admin():
            return Response({'error': 'Only Super Admin can approve shops.'}, status=status.HTTP_403_FORBIDDEN)
        shop = self.get_object()
        shop.status = Shop.Status.APPROVED
        shop.save()
        return Response({'status': 'Approved', 'shop': ShopSerializer(shop).data})

    @action(detail=True, methods=['post'], permission_classes=[permissions.IsAuthenticated])
    def suspend(self, request, pk=None):
        if not request.user.is_super_admin():
            return Response({'error': 'Only Super Admin can suspend shops.'}, status=status.HTTP_403_FORBIDDEN)
        shop = self.get_object()
        shop.status = Shop.Status.SUSPENDED
        shop.save()
        return Response({'status': 'Suspended', 'shop': ShopSerializer(shop).data})

class ShopMembershipViewSet(viewsets.ModelViewSet):
    serializer_class = ShopMembershipSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        if user.is_super_admin():
            return ShopMembership.objects.all()
        if user.is_shop_owner():
            return ShopMembership.objects.filter(shop__owner=user)
        return ShopMembership.objects.filter(user=user)

