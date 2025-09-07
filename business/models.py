# models.py
from django.db import models
from kirazee_app.models import Business, Registration
from datetime import datetime

class BusinessPayment(models.Model):
    id = models.BigAutoField(primary_key=True)
    transaction_id = models.CharField(max_length=100, null=True, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default='INR')
    payment_method = models.CharField(max_length=50, null=True, blank=True)
    status = models.CharField(max_length=50)
    refund_status = models.CharField(max_length=50, null=True, blank=True)
    refund_id = models.CharField(max_length=100, null=True, blank=True)
    upi_id = models.CharField(max_length=100, null=True, blank=True)
    payment_type = models.CharField(max_length=50, null=True, blank=True)
    
    payment_source = models.CharField(max_length=100, null=True, blank=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    user_id = models.ForeignKey(Registration, on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_payments'

def menu_item_upload_path(instance, filename):
    """Generate upload path for menu item images"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    ext = filename.split('.')[-1]
    return f'menuItems/{instance.item_id}_{timestamp}.{ext}'

class MenuItems(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    item_name = models.CharField(max_length=255)
    description = models.TextField(null=True, blank=True)
    item_image = models.ImageField(upload_to=menu_item_upload_path, null=True, blank=True)
    item_category = models.CharField(max_length=100, null=True, blank=True)
    item_type = models.CharField(max_length=100, null=True, blank=True)
    availability_timings = models.JSONField(null=True, blank=True)
    preparation_time = models.CharField(max_length=50, null=True, blank=True)
    quantity = models.IntegerField(null=True, blank=True)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="GST percentage")
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated GST amount")
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'menuItems'
        ordering = ['item_name']

    def save(self, *args, **kwargs):
        # Calculate GST charges if original_cost and gst are provided
        if self.original_cost and self.gst:
            self.charges = (self.original_cost * self.gst) / 100
        
        if self.is_active is None:
            self.is_active = True
        if self.status is None:
            self.status = True

        # Set custom item_id starting from 182250 if not set
        if not self.item_id:
            last_item = MenuItems.objects.order_by('-item_id').first()
            if last_item:
                self.item_id = last_item.item_id + 1
            else:
                self.item_id = 182250
        
        super().save(*args, **kwargs)

    def __str__(self):
        return self.item_name

class BOM(models.Model):
    bom_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(Business, on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    product_id = models.ForeignKey(MenuItems, on_delete=models.CASCADE, to_field='item_id', db_column='product_id')
    ingredients = models.CharField(max_length=100)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    unit = models.CharField(max_length=10)
    cost = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bill_of_materials'
        ordering = ['ingredients']
    
    def save(self, *args, **kwargs):
        if self.status is None:
            self.status = True

        # Set custom bom_id starting from 105501 if not set
        if not self.bom_id:
            last_item = BOM.objects.order_by('-bom_id').first()
            if last_item:
                self.bom_id = last_item.bom_id + 1
            else:
                self.bom_id = 105501
        
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.ingredients} for {self.product_id.item_name}"

class BillOfMaterialsLog(models.Model):
    ACTION_CHOICES = [
        ('INSERT', 'Insert'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
    ]
    
    log_id = models.BigAutoField(primary_key=True)
    bom_id = models.BigIntegerField()
    user_id = models.BigIntegerField(null=True, blank=True)
    action_type = models.CharField(max_length=10, choices=ACTION_CHOICES)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    action_timestamp = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'bill_of_materials_log'
        ordering = ['-action_timestamp']
    
    def __str__(self):
        return f"BOM {self.bom_id} - {self.action_type} at {self.action_timestamp}"

def product_item_upload_path(instance, filename):
    """Generate upload path for product item images"""
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    ext = filename.split('.')[-1]
    return f'productItems/{instance.item_id}_{timestamp}.{ext}'

class productItems(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey(
        Business,
        on_delete=models.CASCADE,
        to_field="business_id",
        db_column="business_id"
    )
    item_name = models.CharField(max_length=255)
    item_image = models.ImageField(
        upload_to=product_item_upload_path, null=True, blank=True
    )
    item_type = models.CharField(max_length=100, null=True, blank=True)
    material = models.CharField(max_length=45, null=True, blank=True)
    gender = models.CharField(max_length=45, null=True, blank=True)
    color = models.CharField(max_length=45, null=True, blank=True)
    item_category = models.CharField(max_length=100, null=True, blank=True)
    description = models.CharField(max_length=100, null=True, blank=True)
    is_organic = models.CharField(max_length=45, null=True, blank=True)
    availability_timings = models.TimeField(null=True, blank=True)
    weight = models.CharField(max_length=45, null=True, blank=True)
    size = models.CharField(max_length=45, null=True, blank=True)
    unit = models.CharField(max_length=10, null=True, blank=True)
    rating = models.DecimalField(max_digits=2, decimal_places=1, null=True, blank=True)
    original_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    gst = models.IntegerField(null=True, blank=True, help_text="GST percentage")
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Calculated GST amount")
    selling_price = models.DecimalField(max_digits=10, decimal_places=2)
    wallet_points_availablity = models.BooleanField(default=False)
    wallet_points = models.BigIntegerField(default=0)
    mfg_data = models.DateField(null=True, blank=True)
    expiry_date = models.DateField(null=True, blank=True)
    stock = models.IntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "Groceries"
        ordering = ["item_name"]

    def save(self, *args, **kwargs):
        # Calculate GST charges if original_cost and gst are provided
        if self.original_cost and self.gst:
            self.charges = (self.original_cost * self.gst) / 100

        if self.is_active is None:
            self.is_active = True
        if self.status is None:
            self.status = True

        # Custom item_id starting point if table empty
        if not self.item_id:
            last_item = productItems.objects.order_by("-item_id").first()
            if last_item:
                self.item_id = last_item.item_id + 1
            else:
                self.item_id = 105501

        super().save(*args, **kwargs)

    def __str__(self):
        return self.item_name
