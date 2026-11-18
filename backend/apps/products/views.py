from django.db.models import Q
from rest_framework import viewsets, permissions, status, views
from rest_framework.decorators import action
from rest_framework.response import Response
from apps.products.models import Category, Product, ProductBarcode
from apps.products.serializers import CategorySerializer, ProductSerializer
from apps.inventory.models import Inventory

class CategoryViewSet(viewsets.ModelViewSet):
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        shop_id = self.request.query_params.get('shop_id')
        qs = Category.objects.all()
        if shop_id:
            qs = qs.filter(Q(shop_id=shop_id) | Q(shop__isnull=True))
        return qs

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        user = self.request.user
        shop_id = self.request.query_params.get('shop_id')
        category_id = self.request.query_params.get('category_id')
        search = self.request.query_params.get('search', '').strip()

        qs = Product.objects.filter(is_active=True).prefetch_related('barcodes').select_related('inventory', 'category', 'shop')
        
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        elif user and user.is_authenticated:
            if user.is_shop_owner():
                qs = qs.filter(shop__owner=user)
            elif user.is_worker():
                qs = qs.filter(shop__memberships__user=user)

        if category_id:
            qs = qs.filter(category_id=category_id)

        if search:
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(sku__icontains=search) |
                Q(brand__icontains=search) |
                Q(barcodes__barcode__icontains=search)
            ).distinct()

        return qs

class BarcodeLookupView(views.APIView):
    """Worker scans a product barcode or enters manually during billing."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def get(self, request, code):
        shop_id = request.query_params.get('shop_id')
        user = request.user
        
        barcode_clean = str(code).strip()
        
        qs = Product.objects.filter(is_active=True)
        if shop_id:
            qs = qs.filter(shop_id=shop_id)
        elif user.is_authenticated and hasattr(user, 'is_shop_owner') and user.is_shop_owner():
            qs = qs.filter(shop__owner=user)
        elif user.is_authenticated and hasattr(user, 'is_worker') and user.is_worker():
            qs = qs.filter(shop__memberships__user=user)

        # Match either barcode or SKU
        product = qs.filter(
            Q(barcodes__barcode__iexact=barcode_clean) |
            Q(sku__iexact=barcode_clean)
        ).first()

        if not product:
            return Response({
                'found': False,
                'barcode': barcode_clean,
                'message': f'No product found for barcode/SKU: {barcode_clean}'
            }, status=status.HTTP_404_NOT_FOUND)

        inv = getattr(product, 'inventory', None)
        current_stock = float(inv.current_stock) if inv else 0.0

        return Response({
            'found': True,
            'barcode': barcode_clean,
            'product': ProductSerializer(product).data,
            'available_stock': current_stock,
            'in_stock': current_stock > 0
        }, status=status.HTTP_200_OK)


def barcode_image_view(request, code):
    """
    Renders an exact 1D Code-128 / EAN barcode image (PNG or SVG)
    matching the product barcode so that scanning it automatically resolves
    the product details and adds it to the cart.
    """
    import barcode
    from barcode.writer import ImageWriter
    from io import BytesIO
    from django.http import HttpResponse

    barcode_clean = str(code).strip()
    fmt = request.GET.get('format', 'png').lower()
    include_text = request.GET.get('text', '1') == '1'

    try:
        if fmt == 'svg':
            code_gen = barcode.get('code128', barcode_clean)
            fp = BytesIO()
            code_gen.write(fp, options={'write_text': include_text})
            return HttpResponse(fp.getvalue(), content_type='image/svg+xml')
        else:
            writer = ImageWriter()
            code_gen = barcode.get('code128', barcode_clean, writer=writer)
            fp = BytesIO()
            code_gen.write(fp, options={
                'write_text': include_text,
                'module_height': 16.0,
                'module_width': 0.35,
                'quiet_zone': 4.0,
                'font_size': 11,
                'text_distance': 4.0,
            })
            resp = HttpResponse(fp.getvalue(), content_type='image/png')
            if request.GET.get('download') == '1':
                resp['Content-Disposition'] = f'attachment; filename="barcode_{barcode_clean}.png"'
            return resp
    except Exception as e:
        svg_err = f'<svg xmlns="http://www.w3.org/2000/svg" width="250" height="60"><text x="10" y="35" fill="red" font-family="sans-serif">Barcode Error: {e}</text></svg>'
        return HttpResponse(svg_err, content_type='image/svg+xml', status=400)


class DecodeBarcodeImageView(views.APIView):
    """Decodes a 1D/2D barcode from an uploaded PNG/JPG image or base64 webcam frame and returns the matched product."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        import base64
        from io import BytesIO
        import zxingcpp
        from PIL import Image, ImageOps

        img = None
        try:
            if 'image' in request.FILES:
                img = Image.open(request.FILES['image'])
            elif request.data.get('image_base64'):
                b64 = str(request.data['image_base64'])
                if ',' in b64:
                    b64 = b64.split(',', 1)[1]
                img = Image.open(BytesIO(base64.b64decode(b64)))
            else:
                return Response({'success': False, 'error': 'Please upload a barcode image file or capture a webcam frame.'}, status=status.HTTP_400_BAD_REQUEST)

            rgb = img.convert('RGB')
            padded = ImageOps.expand(rgb, border=40, fill='white')
            candidates = [
                padded,
                rgb,
                ImageOps.autocontrast(padded.convert('L')),
            ]

            decoded_list = []
            for candidate in candidates:
                res = zxingcpp.read_barcodes(candidate, try_rotate=True, try_downscale=True)
                if res:
                    decoded_list = res
                    break
        except Exception as e:
            return Response({'success': False, 'found': False, 'error': f'Could not read image file: {e}'}, status=status.HTTP_400_BAD_REQUEST)

        if not decoded_list:
            return Response({
                'success': False,
                'found': False,
                'error': 'No readable barcode detected in this image. Try uploading a clear Code-128, EAN-13, or QR barcode image (e.g. downloaded from View Tag -> PNG).'
            }, status=status.HTTP_200_OK)

        barcode_clean = decoded_list[0].text.strip()
        barcode_fmt = str(decoded_list[0].format)

        product = Product.objects.filter(is_active=True).filter(
            Q(barcodes__barcode__iexact=barcode_clean) |
            Q(sku__iexact=barcode_clean)
        ).first()

        if not product:
            return Response({
                'success': True,
                'found': False,
                'decoded_text': barcode_clean,
                'format': barcode_fmt,
                'message': f'Decoded barcode "{barcode_clean}" ({barcode_fmt}), but no product matches it in store catalog.'
            }, status=status.HTTP_200_OK)

        inv = getattr(product, 'inventory', None)
        current_stock = float(inv.current_stock) if inv else 0.0

        return Response({
            'success': True,
            'found': True,
            'decoded_text': barcode_clean,
            'format': barcode_fmt,
            'product': ProductSerializer(product).data,
            'available_stock': current_stock,
            'in_stock': current_stock > 0
        }, status=status.HTTP_200_OK)



