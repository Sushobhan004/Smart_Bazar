from django.urls import path, include
from rest_framework.routers import DefaultRouter
from apps.products.views import ProductViewSet, CategoryViewSet, BarcodeLookupView, barcode_image_view, DecodeBarcodeImageView

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='categories')
router.register(r'', ProductViewSet, basename='products')

urlpatterns = [
    path('barcode/<str:code>/', BarcodeLookupView.as_view(), name='barcode-lookup'),
    path('barcode-image/<str:code>/', barcode_image_view, name='barcode-image'),
    path('decode-barcode-image/', DecodeBarcodeImageView.as_view(), name='decode-barcode-image'),
    path('', include(router.urls)),
]

