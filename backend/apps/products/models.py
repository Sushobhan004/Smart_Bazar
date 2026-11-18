import uuid
from django.db import models
from apps.core.models import TimeStampedModel

class Category(TimeStampedModel):
    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, null=True, blank=True, related_name='categories')
    name = models.CharField(max_length=100, db_index=True)
    icon = models.CharField(max_length=50, blank=True, default='category')
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Categories'
        ordering = ['name']

    def __str__(self):
        return self.name

class Product(TimeStampedModel):
    UNIT_CHOICES = (
        ('PCS', 'Pieces'),
        ('KG', 'Kilogram'),
        ('G', 'Gram'),
        ('LTR', 'Liter'),
        ('ML', 'Milliliter'),
        ('PACK', 'Pack'),
        ('BOX', 'Box'),
    )

    shop = models.ForeignKey('shops.Shop', on_delete=models.CASCADE, related_name='products')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=200, db_index=True)
    sku = models.CharField(max_length=50, blank=True, db_index=True)
    description = models.TextField(blank=True)
    brand = models.CharField(max_length=100, blank=True)
    
    # Financial fields
    purchase_price = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, db_index=True)
    mrp = models.DecimalField(max_digits=10, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0.00, help_text="GST percentage")
    hsn_code = models.CharField(max_length=20, blank=True)
    unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='PCS')
    
    # Alerts
    min_stock_alert = models.PositiveIntegerField(default=5)
    image = models.ImageField(upload_to='product_images/', blank=True, null=True)

    class Meta:
        ordering = ['name']
        unique_together = ('shop', 'sku')

    def __str__(self):
        return f"{self.name} - ₹{self.selling_price}"

    @property
    def primary_barcode(self):
        primary = self.barcodes.filter(is_primary=True).first()
        if not primary:
            primary = self.barcodes.first()
        return primary.barcode if primary else ""

class ProductBarcode(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='barcodes')
    barcode = models.CharField(max_length=100, db_index=True)
    format = models.CharField(max_length=30, default='EAN_13')
    is_primary = models.BooleanField(default=False)

    class Meta:
        unique_together = ('product', 'barcode')
        ordering = ['-is_primary', 'barcode']

    def __str__(self):
        return f"{self.barcode} ({self.product.name})"

class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='variants')
    name = models.CharField(max_length=100)
    sku = models.CharField(max_length=50, blank=True)
    barcode = models.CharField(max_length=100, blank=True)
    price_difference = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    def __str__(self):
        return f"{self.product.name} - {self.name}"

