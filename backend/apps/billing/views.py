import uuid
import secrets
from decimal import Decimal
from django.db import models, transaction
from django.utils import timezone
from django.http import HttpResponse
from rest_framework import views, viewsets, permissions, status
from rest_framework.response import Response

from apps.billing.models import Sale, SaleItem, Invoice, Payment, Return
from apps.billing.serializers import SaleSerializer, CreateSaleRequestSerializer
from apps.products.models import Product
from apps.inventory.models import Inventory, StockTransaction, StockNotification, LOW_STOCK_THRESHOLD
from apps.accounts.models import CustomerProfile
from apps.shops.models import Shop, ShopMembership
from apps.customers.models import CustomerShopAccount, Offer, OfferEligibility, OfferRedemption, RewardLedger

class SaleViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = SaleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        customer_id = self.request.query_params.get('customer_id')

        qs = Sale.objects.select_related('shop', 'worker', 'customer', 'invoice').prefetch_related('items').all()
        if user.is_customer():
            # Customer only sees their own bills
            profile = getattr(user, 'customer_profile', None)
            if profile:
                return qs.filter(customer=profile)
            return Sale.objects.none()

        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        elif user.is_shop_owner():
            qs = qs.filter(shop__owner=user)
        elif user.is_worker():
            qs = qs.filter(shop__memberships__user=user)

        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        return qs

class CreateSaleView(views.APIView):
    """Atomic Bill Creation and POS Checkout"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateSaleRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        shop_id = data['shop_id']
        idempotency_key = data['idempotency_key']

        # Idempotency check: if bill already processed with this key, return existing bill
        existing_sale = Sale.objects.filter(idempotency_key=idempotency_key).first()
        if existing_sale:
            return Response(SaleSerializer(existing_sale).data, status=status.HTTP_200_OK)

        shop = Shop.objects.filter(id=shop_id, status=Shop.Status.APPROVED).first()
        if not shop:
            return Response({'error': 'Invalid or inactive shop.'}, status=status.HTTP_400_BAD_REQUEST)

        # Worker permission check
        worker = request.user
        if not (worker.is_super_admin() or shop.owner == worker or shop.memberships.filter(user=worker, is_active=True).exists()):
            return Response({'error': 'You do not have permission to bill for this shop.'}, status=status.HTTP_403_FORBIDDEN)

        customer = None
        if not data.get('is_guest') and data.get('customer_id'):
            customer = CustomerProfile.objects.filter(id=data['customer_id']).first()

        items_data = data['items']
        if not items_data:
            return Response({'error': 'Cart cannot be empty.'}, status=status.HTTP_400_BAD_REQUEST)

        # Begin atomic transaction with row locking
        with transaction.atomic():
            product_ids = [item['product_id'] for item in items_data]
            # Lock products and inventories
            products = {
                str(p.id): p
                for p in Product.objects.select_for_update().filter(id__in=product_ids, shop=shop, is_active=True)
            }
            inventories = {
                str(inv.product_id): inv
                for inv in Inventory.objects.select_for_update().filter(product_id__in=product_ids, shop=shop)
            }

            # Pre-validate inventory before making changes
            for item in items_data:
                pid = str(item['product_id'])
                if pid not in products:
                    return Response({'error': f'Product {pid} not found in this shop.'}, status=status.HTTP_400_BAD_REQUEST)
                
                inv = inventories.get(pid)
                req_qty = item['quantity']
                avail_qty = inv.current_stock if inv else Decimal('0.00')
                if avail_qty < req_qty:
                    prod = products[pid]
                    return Response({
                        'error': f'Insufficient stock for "{prod.name}". Available: {avail_qty}, Requested: {req_qty}.'
                    }, status=status.HTTP_400_BAD_REQUEST)

            # Calculate billing figures
            subtotal = Decimal('0.00')
            total_tax = Decimal('0.00')
            total_discount = Decimal('0.00')
            sale_items_to_create = []

            for item in items_data:
                pid = str(item['product_id'])
                product = products[pid]
                inv = inventories[pid]
                qty = Decimal(str(item['quantity']))
                discount = Decimal(str(item.get('discount', '0.00')))
                
                unit_price = product.selling_price
                line_subtotal = (unit_price * qty) - discount
                tax_rate = product.tax_rate
                tax_amount = (line_subtotal * (tax_rate / Decimal('100.00'))).quantize(Decimal('0.01'))
                line_total = line_subtotal + tax_amount

                subtotal += (unit_price * qty)
                total_discount += discount
                total_tax += tax_amount

                sale_items_to_create.append({
                    'product': product,
                    'product_name': product.name,
                    'barcode': product.primary_barcode,
                    'quantity': qty,
                    'unit_price': unit_price,
                    'tax_rate': tax_rate,
                    'tax_amount': tax_amount,
                    'discount': discount,
                    'total_price': line_total,
                    'inv': inv
                })

            # Check voucher code if provided
            voucher_code = data.get('voucher_code', '').strip()
            voucher_saving = Decimal('0.00')
            applied_offer = None
            if voucher_code and customer:
                eligibility = OfferEligibility.objects.select_for_update().filter(
                    voucher_code=voucher_code,
                    customer=customer,
                    is_redeemed=False
                ).first()
                if eligibility and eligibility.offer.is_active:
                    applied_offer = eligibility.offer
                    if applied_offer.discount_type == Offer.DiscountType.FLAT:
                        voucher_saving = min(applied_offer.reward_value, subtotal)
                    else:
                        voucher_saving = min((subtotal * applied_offer.reward_value / Decimal('100.00')), applied_offer.max_discount)
                    total_discount += voucher_saving
                    eligibility.is_redeemed = True
                    eligibility.redeemed_at = timezone.now()
                    eligibility.save()

            gross_total = subtotal - total_discount + total_tax
            round_off = (Decimal(round(gross_total)) - gross_total).quantize(Decimal('0.01'))
            final_total = Decimal(round(gross_total))

            # Generate unique Bill Number (e.g. SB-INV-202611-10042)
            today_str = timezone.now().strftime('%Y%m')
            count = Sale.objects.filter(shop=shop, created_at__year=timezone.now().year, created_at__month=timezone.now().month).count() + 1
            bill_number = f"SB-INV-{today_str}-{count:05d}"

            # Create Sale Record
            sale = Sale.objects.create(
                shop=shop,
                worker=worker,
                customer=customer,
                bill_number=bill_number,
                is_guest=data.get('is_guest', False),
                guest_name=data.get('guest_name', ''),
                guest_phone=data.get('guest_phone', ''),
                subtotal=subtotal,
                tax_amount=total_tax,
                discount_amount=total_discount,
                round_off=round_off,
                final_total=final_total,
                payment_method=data.get('payment_method', Sale.PaymentMethod.CASH),
                payment_status=Sale.PaymentStatus.COMPLETED,
                idempotency_key=idempotency_key,
                notes=data.get('notes', '')
            )

            # Deduct stock atomically and create SaleItems & StockTransactions
            for sit in sale_items_to_create:
                SaleItem.objects.create(
                    sale=sale,
                    product=sit['product'],
                    product_name=sit['product_name'],
                    barcode=sit['barcode'],
                    quantity=sit['quantity'],
                    unit_price=sit['unit_price'],
                    tax_rate=sit['tax_rate'],
                    tax_amount=sit['tax_amount'],
                    discount=sit['discount'],
                    total_price=sit['total_price']
                )

                inv = sit['inv']
                inv.current_stock -= sit['quantity']
                inv.save()

                StockTransaction.objects.create(
                    shop=shop,
                    product=sit['product'],
                    tx_type=StockTransaction.TxType.SALE,
                    quantity=-sit['quantity'],
                    balance_after=inv.current_stock,
                    reference_id=bill_number,
                    performed_by=worker,
                    notes=f"POS Sale #{bill_number}"
                )

            # Record Payment
            Payment.objects.create(
                sale=sale,
                amount=final_total,
                payment_method=sale.payment_method,
                transaction_id=f"TXN-{secrets.randbelow(900000) + 100000}",
                is_success=True
            )

            # UPI Dynamic QR or Verification Link
            upi_qr = (
                f"upi://pay?pa={shop.upi_vpa or 'smartbazaar@okaxis'}&pn={shop.name}"
                f"&am={final_total}&cu=INR&tn=Bill-{bill_number}"
            )
            invoice = Invoice.objects.create(
                sale=sale,
                invoice_number=f"INV-{bill_number}",
                qr_data=upi_qr,
                sent_to_email=customer.email if customer else ''
            )

            # If registered customer: update purchase stats & evaluate offers
            if customer:
                customer.total_spent = Decimal(str(customer.total_spent)) + final_total
                customer.visit_count += 1
                # Earn loyalty points: 1 pt per ₹100
                pts_earned = int(final_total // 100)
                customer.reward_points += pts_earned
                customer.save()

                if pts_earned > 0:
                    RewardLedger.objects.create(
                        customer=customer,
                        shop=shop,
                        sale=sale,
                        action=RewardLedger.Action.EARNED,
                        points=pts_earned,
                        balance_after=customer.reward_points,
                        description=f"Points earned on Bill #{bill_number}"
                    )

                shop_account, _ = CustomerShopAccount.objects.get_or_create(customer=customer, shop=shop)
                shop_account.shop_total_spent = Decimal(str(shop_account.shop_total_spent)) + final_total
                shop_account.visit_count += 1
                shop_account.last_visit = timezone.now()
                shop_account.save()

                # Record redemption if offer used
                if applied_offer:
                    OfferRedemption.objects.create(
                        offer=applied_offer,
                        customer=customer,
                        sale=sale,
                        amount_saved=voucher_saving
                    )

                # Check if this sale qualifies customer for any spend-threshold offers!
                # E.g., cumulative spend >= ₹15,000 generates ₹50 voucher
                qualifying_offers = Offer.objects.filter(
                    models.Q(shop=shop) | models.Q(shop__isnull=True),
                    is_active=True,
                    valid_from__lte=timezone.now(),
                    valid_until__gte=timezone.now()
                )
                for off in qualifying_offers:
                    qualified = False
                    if off.calculation_method == Offer.CalculationMethod.SINGLE_BILL and final_total >= off.min_spend_required:
                        qualified = True
                    elif off.calculation_method == Offer.CalculationMethod.LIFETIME and customer.total_spent >= off.min_spend_required:
                        qualified = True
                    elif off.calculation_method == Offer.CalculationMethod.MONTHLY_CUMULATIVE and shop_account.shop_total_spent >= off.min_spend_required:
                        qualified = True

                    if qualified:
                        # Check if voucher already awarded
                        if not OfferEligibility.objects.filter(offer=off, customer=customer).exists():
                            voucher_str = f"SB-REWARD-{secrets.randbelow(900000) + 100000}"
                            OfferEligibility.objects.create(
                                offer=off,
                                customer=customer,
                                voucher_code=voucher_str
                            )

        payload = dict(SaleSerializer(sale).data)
        alerts = [
            {
                'product_id': str(n.product_id),
                'product_name': n.product.name,
                'current_stock': float(n.current_stock),
                'threshold': LOW_STOCK_THRESHOLD,
                'severity': n.severity,
                'title': n.title,
                'message': n.message,
            }
            for n in StockNotification.objects.filter(shop=shop, is_resolved=False).select_related('product')
        ]
        payload['low_stock_alerts'] = alerts
        return Response(payload, status=status.HTTP_201_CREATED)

class ThermalReceiptView(views.APIView):
    """Generates formatted plain text for Bluetooth thermal POS printers (58mm/80mm)."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, sale_id):
        sale = Sale.objects.select_related('shop', 'worker', 'customer', 'invoice').prefetch_related('items').filter(id=sale_id).first()
        if not sale:
            return Response({'error': 'Sale not found.'}, status=status.HTTP_404_NOT_FOUND)

        shop = sale.shop
        lines = []
        lines.append("=" * 32)
        lines.append(f"{shop.name.center(32)}")
        lines.append(f"{shop.address[:32].center(32)}")
        if shop.phone:
            lines.append(f"Phone: {shop.phone}".center(32))
        if shop.gstin:
            lines.append(f"GSTIN: {shop.gstin}".center(32))
        lines.append("=" * 32)
        lines.append(f"Bill No : {sale.bill_number}")
        lines.append(f"Date    : {sale.created_at.strftime('%d-%b-%Y %I:%M %p')}")
        lines.append(f"Cashier : {sale.worker.username}")
        if sale.customer:
            lines.append(f"Customer: {sale.customer.full_name} ({sale.customer.masked_phone})")
        else:
            lines.append("Customer: Guest")
        lines.append("-" * 32)
        lines.append(f"{'Item':<16}{'Qty':<4}{'Price':>6}{'Total':>6}")
        lines.append("-" * 32)

        for it in sale.items.all():
            name = it.product_name[:15]
            qty_str = f"{it.quantity:.0f}"
            price_str = f"{it.unit_price:.1f}"
            tot_str = f"{it.total_price:.1f}"
            lines.append(f"{name:<16}{qty_str:<4}{price_str:>6}{tot_str:>6}")

        lines.append("-" * 32)
        lines.append(f"{'Subtotal:':<22}{sale.subtotal:>10.2f}")
        if sale.discount_amount > 0:
            lines.append(f"{'Discount:':<22}{(-sale.discount_amount):>10.2f}")
        if sale.tax_amount > 0:
            lines.append(f"{'GST/Tax:':<22}{sale.tax_amount:>10.2f}")
        if sale.round_off != 0:
            lines.append(f"{'Round Off:':<22}{sale.round_off:>10.2f}")
        lines.append("=" * 32)
        lines.append(f"{'NET PAYABLE:':<18} Rs.{sale.final_total:>10.2f}")
        lines.append("=" * 32)
        lines.append(f"Payment Mode: {sale.payment_method}")
        lines.append(f"Status      : {sale.payment_status}")
        lines.append("")
        lines.append("Thank you for shopping at Smart Bazaar!".center(32))
        lines.append("Goods once sold can be returned".center(32))
        lines.append("within 7 days with this receipt.".center(32))
        lines.append("=" * 32)

        receipt_text = "\n".join(lines)
        return Response({
            'bill_number': sale.bill_number,
            'receipt_text': receipt_text,
            'qr_data': sale.invoice.qr_data if hasattr(sale, 'invoice') else ''
        }, status=status.HTTP_200_OK)
