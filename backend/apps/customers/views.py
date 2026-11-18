from django.db import models
from rest_framework import views, viewsets, permissions, status
from rest_framework.response import Response
from apps.customers.models import CustomerShopAccount, Offer, OfferEligibility, RewardLedger, CustomerNotification
from apps.customers.serializers import (
    OfferSerializer, OfferEligibilitySerializer, RewardLedgerSerializer,
    CustomerShopAccountSerializer, CustomerNotificationSerializer
)
from apps.billing.models import Sale
from apps.billing.serializers import SaleSerializer

class OfferViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = OfferSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        shop_id = self.request.query_params.get('shop_id')
        qs = Offer.objects.filter(is_active=True)
        if shop_id:
            qs = qs.filter(models.Q(shop_id=shop_id) | models.Q(shop__isnull=True))
        return qs

class CustomerSummaryView(views.APIView):
    """Customer spending analytics: total spend, shop-wise spend, reward wallet, recent bills."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        if not user.is_customer():
            return Response({'error': 'Only customer accounts can access customer summary.'}, status=status.HTTP_403_FORBIDDEN)

        profile = getattr(user, 'customer_profile', None)
        if not profile:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Shop-wise breakdown
        shop_accounts = CustomerShopAccount.objects.filter(customer=profile).select_related('shop')
        shop_breakdown = CustomerShopAccountSerializer(shop_accounts, many=True).data

        # Vouchers & rewards
        vouchers = OfferEligibility.objects.filter(customer=profile, is_redeemed=False).select_related('offer')
        voucher_data = OfferEligibilitySerializer(vouchers, many=True).data

        # Recent bills
        recent_sales = Sale.objects.filter(customer=profile).select_related('shop', 'invoice').order_by('-created_at')[:10]
        recent_bills_data = SaleSerializer(recent_sales, many=True).data

        # Notifications
        notifications = CustomerNotification.objects.filter(customer=profile, is_read=False)[:5]
        notification_data = CustomerNotificationSerializer(notifications, many=True).data

        return Response({
            'customer_code': profile.customer_code,
            'full_name': profile.full_name,
            'email': profile.email,
            'phone_number': profile.phone_number,
            'total_spent': float(profile.total_spent),
            'visit_count': profile.visit_count,
            'reward_points': profile.reward_points,
            'wallet_balance': float(profile.wallet_balance),
            'shop_wise_spending': shop_breakdown,
            'available_vouchers': voucher_data,
            'recent_bills': recent_bills_data,
            'unread_notifications': notification_data
        }, status=status.HTTP_200_OK)

class CustomerWalletView(views.APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        profile = getattr(request.user, 'customer_profile', None)
        if not profile:
            return Response({'error': 'Profile not found.'}, status=status.HTTP_404_NOT_FOUND)

        vouchers = OfferEligibility.objects.filter(customer=profile).select_related('offer')
        ledger = RewardLedger.objects.filter(customer=profile)[:20]

        return Response({
            'reward_points': profile.reward_points,
            'wallet_balance': float(profile.wallet_balance),
            'vouchers': OfferEligibilitySerializer(vouchers, many=True).data,
            'points_ledger': RewardLedgerSerializer(ledger, many=True).data
        }, status=status.HTTP_200_OK)

