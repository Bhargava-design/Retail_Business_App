from django.db import models
from django.utils import timezone
import os
import time

def business_logo_path(instance, filename):
    ext = filename.split('.')[-1]
    timestamp = int(time.time())
    filename = f"{instance.business_id}_{timestamp}.{ext}"
    return os.path.join("media/business_logos", filename)

def business_banner_path(instance, filename):
    ext = filename.split('.')[-1]
    timestamp = int(time.time())
    filename = f"{instance.business_id}_{timestamp}.{ext}"
    return os.path.join("media/business_banners", filename)

# ==============================================================================
# 1️⃣ User Management Tables - CORRECTED
# ==============================================================================

class Registration(models.Model):
    # Note: The 'id' primary key is automatically created by Django.
    user_id = models.BigIntegerField(unique=True, editable=False)
    firstName = models.CharField(max_length=100)
    lastName = models.CharField(max_length=100)
    countryCode = models.CharField(max_length=10)
    mobileNumber = models.CharField(max_length=15,unique=True, db_column='mobileNumber')
    emailID = models.EmailField(max_length=255, unique=True)
    dob = models.DateField(null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    user_mode = models.CharField(max_length=255, default='consumer')
    profileUrl = models.CharField(max_length=255, null=True, blank=True)
    tokenID = models.CharField(max_length=255, null=True, blank=True, db_column='tokenID')
    uuid = models.CharField(max_length=100, null=True, blank=True)
    os = models.CharField(max_length=50, null=True, blank=True)
    status = models.BooleanField(default=True)
    whichapp = models.CharField(max_length=50, default='Kirazee')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        # This tells Django which table to use.
        db_table = 'registrations'


class Otp(models.Model):
    mobileNumber = models.ForeignKey(
        Registration,
        to_field='mobileNumber',
        on_delete=models.CASCADE,
        db_column='mobileNumber',
        related_name='otps'
    )
    emailID = models.CharField(max_length=255, null=True, blank=True)
    tokenID = models.CharField(max_length=255, null=True, blank=True)
    code = models.CharField(max_length=6)
    # status 0 = not verified, 1 = verified
    status = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'otps'


# ============================================================================== 
# 2️⃣ User Address Table
# ============================================================================== 

class UserAddress(models.Model):
    id = models.BigAutoField(primary_key=True)
    # Link to Registration via user_id numeric column
    user = models.ForeignKey(
        Registration,
        to_field='user_id',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='addresses'
    )
    address_type = models.CharField(max_length=10, null=True, blank=True)
    tag = models.CharField(max_length=50, null=True, blank=True)
    is_default = models.BooleanField(default=False)
    address = models.JSONField()
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_address'


# ============================================================================== 
# 3️⃣ Business Domain Tables
# ============================================================================== 

class BusinessType(models.Model):
    code = models.CharField(max_length=10, primary_key=True)
    type = models.CharField(max_length=100)
    categories = models.JSONField()
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_types'
        managed = False


class BusinessFeature(models.Model):
    feature_id = models.CharField(max_length=10, primary_key=True)
    details = models.CharField(max_length=255)
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_features'
        managed = False


class Business(models.Model):
    business_id = models.CharField(max_length=50, primary_key=True)
    level = models.CharField(max_length=50, default='Master Level', null=True, blank=True)
    master = models.CharField(max_length=50, null=True, blank=True)
    businessName = models.CharField(max_length=255)
    businessType = models.CharField(max_length=10)
    businessCategory = models.CharField(max_length=255)
    businessEmail = models.CharField(max_length=255, null=True, blank=True)
    businessNumber = models.CharField(max_length=15, null=True, blank=True)
    businessWhatsapp = models.CharField(max_length=15, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    logo = models.ImageField(upload_to=business_logo_path, max_length=255, null=True, blank=True)
    banner = models.ImageField(upload_to=business_banner_path, max_length=255, null=True, blank=True)
    business_licence = models.CharField(max_length=255, null=True, blank=True)
    business_features = models.JSONField(null=True, blank=True)
    business_hours = models.JSONField(null=True, blank=True)
    gst_num = models.CharField(max_length=50, null=True, blank=True)
    currency = models.CharField(max_length=10, default='INR')
    location = models.CharField(max_length=255, null=True, blank=True)
    address = models.TextField(null=True, blank=True)
    landmark = models.CharField(max_length=255, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    state = models.CharField(max_length=100, null=True, blank=True)
    pincode = models.CharField(max_length=20, null=True, blank=True)
    contact_support = models.CharField(max_length=255, null=True, blank=True)
    contact_mobile = models.CharField(max_length=15, null=True, blank=True)
    website_url = models.CharField(max_length=255, null=True, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_verified = models.BooleanField(default=False)
    status = models.BooleanField(default=True)
    paymentstatus = models.BooleanField(default=False)
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'businesses'
        managed = False

    def save(self, *args, **kwargs):
        # Update latitude and longitude from location if it exists
        if self.location:
            self.longitude = self.location.x
            self.latitude = self.location.y
        super().save(*args, **kwargs)

class BusinessFinancial(models.Model):
    id = models.BigAutoField(primary_key=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE)
    owner_pan = models.CharField(max_length=20, null=True, blank=True)
    gstin = models.CharField(max_length=20, null=True, blank=True)
    ifsc_code = models.CharField(max_length=20, null=True, blank=True)
    account_number = models.CharField(max_length=50, null=True, blank=True)
    razor_pay_key_id = models.CharField(max_length=100, null=True, blank=True)
    razor_pay_key_code = models.CharField(max_length=100, null=True, blank=True)
    razor_webhook_secret = models.CharField(max_length=255, null=True, blank=True)
    fssai_certification_number = models.CharField(max_length=50, null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "business_financials"
        verbose_name = "Business Financial"
        verbose_name_plural = "Business Financials"

    def __str__(self):
        return f"Financials for {self.business.business_id}"

class BusinessMapping(models.Model):
    id = models.BigAutoField(primary_key=True)
    # UNIQUE KEY on user_id -> model as OneToOne to Registration.user_id
    user = models.OneToOneField(
        'Registration',
        to_field='user_id',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='business_mapping',
    )
    business = models.ForeignKey(
        'Business',
        to_field='business_id',
        db_column='business_id',
        on_delete=models.CASCADE,
        related_name='user_mappings',
    )
    status = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_mapping'
        managed = False


class BusinessOwnerDetails(models.Model):
    id = models.BigAutoField(primary_key=True)
    # FK references business_mapping(user_id), not its PK. Point to the OneToOne field 'user'.
    user = models.ForeignKey(
        'BusinessMapping',
        to_field='user',
        db_column='user_id',
        on_delete=models.CASCADE,
        related_name='owner_details',
    )
    pan = models.CharField(max_length=20, null=True, blank=True)
    aadhaar = models.CharField(max_length=20, null=True, blank=True)
    per_mobile_number = models.CharField(max_length=15, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'business_owner_details'
        managed = False


# ============================================================================== 
# 4️⃣ Navigation System Tables
# ============================================================================== 

class NavigationItem(models.Model):
    id = models.CharField(max_length=50, primary_key=True)
    label = models.CharField(max_length=100)
    icon_svg = models.TextField(null=True, blank=True)
    order = models.BigIntegerField(null=True, blank=True)
    is_visible = models.BooleanField(default=True)
    mode = models.CharField(max_length=50, null=True, blank=True)
    route_path = models.CharField(max_length=100, null=True, blank=True)
    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        db_column='parent_id',
        related_name='children'
    )

    class Meta:
        db_table = 'NavigationItem'
        managed = False
        ordering = ['order', 'label']

    def __str__(self):
        return f"{self.label} ({self.mode})"
