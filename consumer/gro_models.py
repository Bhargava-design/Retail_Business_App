from django.db import models
from kirazee_app.models import Business, Registration, BusinessFeature, BusinessType, BusinessMapping, BusinessOwnerDetails
from business.models import MenuItems, productItems, BOM, BillOfMaterialsLog, BusinessPayment
from datetime import datetime
import json
import random
import string



class Groceries(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id')
    item_name = models.CharField(max_length=255)
    item_image = models.CharField(max_length=255, null=True, blank=True)
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
    gst = models.IntegerField(null=True, blank=True)
    charges = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    selling_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
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
        db_table = 'Groceries'


class GroceriesCart(models.Model):
    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id')
    item = models.ForeignKey(Groceries, on_delete=models.CASCADE, db_column='item_id')
    quantity = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id', null=True, blank=True)

    class Meta:
        db_table = 'Groceries_cart'


class GroceriesOrders(models.Model):
    ORDER_TYPE_CHOICES = [('pickup', 'Pickup'), ('delivery', 'Delivery')]
    ORDER_STATUS_CHOICES = [('pending', 'Pending'), ('confirmed', 'Confirmed'), ('shipped', 'Shipped'), ('delivered', 'Delivered'), ('cancelled', 'Cancelled')]
    PAYMENT_STATUS_CHOICES = [('pending', 'Pending'), ('paid', 'Paid'), ('failed', 'Failed'), ('refunded', 'Refunded')]

    order_id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id')
    order_type = models.CharField(max_length=10, choices=ORDER_TYPE_CHOICES)
    order_status = models.CharField(max_length=10, choices=ORDER_STATUS_CHOICES, default='pending')
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    total_amount = models.DecimalField(max_digits=10, decimal_places=2)
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    delivery_charge = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    discount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    final_amount = models.DecimalField(max_digits=10, decimal_places=2)
    delivery_address = models.TextField(null=True, blank=True)
    pickup_time = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Groceries_orders'


class GroceriesOrderItems(models.Model):
    order_item_id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(GroceriesOrders, on_delete=models.CASCADE, db_column='order_id')
    item = models.ForeignKey(Groceries, on_delete=models.CASCADE, db_column='item_id')
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    gst = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)
    total_price = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'Groceries_order_items'


class GroceriesPayments(models.Model):
    PAYMENT_METHOD_CHOICES = [('cash', 'Cash'), ('card', 'Card'), ('upi', 'UPI'), ('wallet', 'Wallet')]
    PAYMENT_STATUS_CHOICES = [('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed'), ('refunded', 'Refunded')]

    payment_id = models.BigAutoField(primary_key=True)
    order = models.ForeignKey(GroceriesOrders, on_delete=models.CASCADE, db_column='order_id')
    user = models.ForeignKey(Registration, on_delete=models.CASCADE, db_column='user_id')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_method = models.CharField(max_length=10, choices=PAYMENT_METHOD_CHOICES)
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=255, null=True, blank=True)
    payment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'Groceries_payments'


class GroceryPartner(models.Model):
    VEHICLE_TYPE_CHOICES = [
        ('bike', 'Bike'),
        ('scooter', 'Scooter'),
        ('car', 'Car'),
        ('van', 'Van'),
        ('truck', 'Truck'),
        ('bicycle', 'Bicycle'),
        ('auto', 'Auto Rickshaw'),
    ]
    
    AVAILABILITY_STATUS_CHOICES = [
        ('available', 'Available'),
        ('busy', 'Busy'),
        ('offline', 'Offline'),
        ('break', 'Break'),
    ]

    id = models.AutoField(primary_key=True)
    user = models.OneToOneField(Registration, on_delete=models.CASCADE, db_column='user_id', to_field='user_id')
    business = models.ForeignKey(Business, on_delete=models.CASCADE, db_column='business_id', to_field='business_id', null=True, blank=True)
    vehicle_number = models.CharField(max_length=20, unique=True)
    vehicle_type = models.CharField(max_length=20, choices=VEHICLE_TYPE_CHOICES)
    driving_license_number = models.CharField(max_length=20, unique=True)
    aadhar_card_number = models.CharField(max_length=12, unique=True)
    bank_account_number = models.CharField(max_length=20, null=True, blank=True)
    bank_ifsc_code = models.CharField(max_length=11, null=True, blank=True)
    bank_account_holder_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_name = models.CharField(max_length=100, null=True, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, null=True, blank=True)
    delivery_zones = models.JSONField(null=True, blank=True, help_text="Store array of delivery area codes")
    current_latitude = models.DecimalField(max_digits=10, decimal_places=8, null=True, blank=True)
    current_longitude = models.DecimalField(max_digits=11, decimal_places=8, null=True, blank=True)
    availability_status = models.CharField(max_length=10, choices=AVAILABILITY_STATUS_CHOICES, default='offline')
    rating_average = models.DecimalField(max_digits=3, decimal_places=2, default=0.00)
    total_deliveries = models.IntegerField(default=0)
    is_verified = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    joined_date = models.DateField()
    last_active_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Grocery_partner'
        indexes = [
            models.Index(fields=['availability_status']),
            models.Index(fields=['current_latitude', 'current_longitude']),
        ]

    def __str__(self):
        return f"Partner {self.user.first_name} {self.user.last_name} - {self.vehicle_number}"

    def set_delivery_zones(self, zones_list):
        """Helper method to set delivery zones as JSON"""
        self.delivery_zones = zones_list

    def get_delivery_zones(self):
        """Helper method to get delivery zones from JSON"""
        return self.delivery_zones if self.delivery_zones else []


class GroceryDeliverDetails(models.Model):
    ASSIGNMENT_STATUS_CHOICES = [
        ('assigned', 'Assigned'),
        ('accepted', 'Accepted'),
        ('picked_up', 'Picked Up'),
        ('in_transit', 'In Transit'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    delivery_detail_id = models.BigAutoField(primary_key=True)
    order = models.OneToOneField(
        GroceriesOrders, 
        on_delete=models.CASCADE, 
        db_column='order_id',
        unique=True,
        help_text="Each order can only have one delivery assignment"
    )
    partner = models.ForeignKey(
        GroceryPartner, 
        on_delete=models.RESTRICT, 
        db_column='partner_id',
        help_text="Delivery partner assigned to this order"
    )
    assigned_by_user = models.ForeignKey(
        Registration, 
        on_delete=models.RESTRICT, 
        db_column='assigned_by_user_id',
        help_text="User who assigned this order to the partner"
    )
    assignment_status = models.CharField(
        max_length=20, 
        choices=ASSIGNMENT_STATUS_CHOICES, 
        default='assigned',
        help_text="Current status of the delivery assignment"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_otp = models.CharField(
        max_length=6, 
        null=True, 
        blank=True,
        help_text="OTP for delivery verification"
    )
    otp_verified_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'Grocery_deliver_details'
        indexes = [
            models.Index(fields=['partner', 'assignment_status'], name='idx_partner_status'),
            models.Index(fields=['order'], name='idx_order_delivery'),
        ]

    def __str__(self):
        return f"Delivery {self.delivery_detail_id} - Order {self.order.order_id} - {self.assignment_status}"

    def generate_otp(self):
        """Generate a 6-digit OTP for delivery verification"""
        self.delivery_otp = ''.join(random.choices(string.digits, k=6))
        self.save(update_fields=['delivery_otp'])
        return self.delivery_otp

    def verify_otp(self, otp):
        """Verify the provided OTP and mark as verified if correct"""
        if self.delivery_otp == otp:
            self.otp_verified_at = datetime.now()
            self.save(update_fields=['otp_verified_at'])
            return True
        return False

    def mark_delivered(self):
        """Mark the delivery as completed"""
        self.assignment_status = 'delivered'
        self.delivered_at = datetime.now()
        self.save(update_fields=['assignment_status', 'delivered_at'])

    def can_update_status(self, new_status):
        """Check if status transition is valid"""
        valid_transitions = {
            'assigned': ['accepted', 'cancelled'],
            'accepted': ['picked_up', 'cancelled'],
            'picked_up': ['in_transit', 'cancelled'],
            'in_transit': ['delivered', 'cancelled'],
            'delivered': [],  # Final state
            'cancelled': [],  # Final state
        }
        return new_status in valid_transitions.get(self.assignment_status, [])

