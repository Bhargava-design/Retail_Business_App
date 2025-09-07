from django.db import models, transaction
from django.utils import timezone
from django_fsm import FSMField, transition  # Temporary revert
from decimal import Decimal
import uuid
import json
from datetime import datetime, timedelta
from kirazee_app.models import Business, Registration, BusinessFeature, BusinessType, BusinessMapping, BusinessOwnerDetails, UserAddress
from business.models import MenuItems, productItems, BOM, BillOfMaterialsLog, BusinessPayment

class MenuCart(models.Model):
    id = models.PositiveBigIntegerField(primary_key=True)
    user_id = models.BigIntegerField()
    menu_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business_id = models.CharField(max_length=50, null=True, blank=True)  

    class Meta:
        db_table = "menuCart"

    def save(self, *args, **kwargs):
        if not self.id:
            last_item = MenuCart.objects.order_by('-id').first()
            if last_item:
                self.id = last_item.id + 1
            else:
                self.id = 1101
        super().save(*args, **kwargs)

    def __str__(self):
        return str(self.id)

class GrocerieCart(models.Model):
    id = models.BigAutoField(primary_key=True)
    user_id = models.BigIntegerField()
    item_id = models.BigIntegerField()
    quantity = models.PositiveIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    business_id = models.CharField(max_length=45, null=True, blank=True)

    class Meta:
        db_table = "Groceries_cart"

    def save(self, *args, **kwargs):
        if not self.id:
            last_item = GrocerieCart.objects.order_by('-id').first()
            if last_item:
                self.id = last_item.id + 1
            else:
                self.id = 1101
        super().save(*args, **kwargs)

    def __str__(self):
        return f"GrocerieCart {self.id} - User {self.user_id}"

class Orders(models.Model):
    class OrderStatus(models.TextChoices):
        PENDING = 'pending', 'Pending'
        CONFIRMED = 'confirmed', 'Confirmed'
        PREPARING = 'preparing', 'Preparing'
        READY = 'ready', 'Ready'
        DISPATCHED = 'dispatched', 'Dispatched'
        OUT_FOR_DELIVERY = 'out_for_delivery', 'Out for Delivery'
        DELIVERED = 'delivered', 'Delivered'
        CANCELLED = 'cancelled', 'Cancelled'
        TRAVELLING = 'travelling', 'Travelling'
        OUT_FOR_DELIVERY_GROCERY = 'out_for_delivery_grocery', 'Out for Delivery (Grocery)'
    
    class OrderType(models.TextChoices):
        DELIVERY = 'delivery', 'Delivery'
        PICKUP = 'pickup', 'Pickup'
        DINE_IN = 'dine_in', 'Dine In'
        TAKEAWAY = 'takeaway', 'Takeaway'
    
    order_id = models.BigAutoField(primary_key=True)
    order_number = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.SET_NULL, null=True, blank=True, to_field='user_id', db_column='user_id')
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    order_type = models.CharField(max_length=20, choices=OrderType.choices, default=OrderType.DELIVERY)
    status = FSMField(default=OrderStatus.PENDING, choices=OrderStatus.choices)
    
    # Financial fields
    total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    delivery_charges = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    final_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Address fields with Historical Immutability
    delivery_address_snapshot = models.JSONField(null=True, blank=True, help_text="Snapshot of delivery address at order time")
    billing_address_snapshot = models.JSONField(null=True, blank=True, help_text="Snapshot of billing address at order time")
    delivery_address = models.ForeignKey('kirazee_app.UserAddress', on_delete=models.SET_NULL, null=True, blank=True, related_name='delivery_orders')
    
    # Coupon and wallet fields
    coupon_code = models.CharField(max_length=50, null=True, blank=True)
    wallet_points_used = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.00'))
    
    # Timing fields
    estimated_delivery_time = models.DateTimeField(null=True, blank=True)
    actual_delivery_time = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'orders'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.order_id:
            last_order = Orders.objects.order_by('-order_id').first()
            if last_order:
                self.order_id = last_order.order_id + 1
            else:
                self.order_id = 1001
        super().save(*args, **kwargs)
    
    def _create_address_snapshot(self, address):
        """Create JSON snapshot of address for historical immutability"""
        if not address:
            return None
            
        try:
            # Get address data from JSON field
            address_data = address.address
            
            return {
                'state': address_data.get('state'),
                'street': address_data.get('street'),
                'door_no': address_data.get('Door no'),
                'country': address_data.get('country'),
                'pincode': address_data.get('pincode'),
                'city': address_data.get('city/town'),
                'latitude': address_data.get('latitude'),
                'longitude': address_data.get('longitude'),
                'address_type': address.address_type,
                'snapshot_created_at': timezone.now().isoformat()
            }
        except Exception:
            return None
    
    # FSM Transitions
    @transition(field=status, source=OrderStatus.PENDING, target=OrderStatus.CONFIRMED)
    def confirm_order(self):
        pass
    
    @transition(field=status, source=OrderStatus.CONFIRMED, target=OrderStatus.PREPARING)
    def start_preparing(self):
        pass
    
    @transition(field=status, source=OrderStatus.PREPARING, target=OrderStatus.READY)
    def mark_ready(self):
        pass
    
    @transition(field=status, source=OrderStatus.READY, target=OrderStatus.DISPATCHED)
    def dispatch_for_delivery(self):
        pass
    
    @transition(field=status, source=OrderStatus.DISPATCHED, target=OrderStatus.TRAVELLING)
    def start_travelling(self):
        pass
    
    @transition(field=status, source=OrderStatus.TRAVELLING, target=OrderStatus.OUT_FOR_DELIVERY_GROCERY)
    def out_for_delivery_grocery(self):
        pass
    
    @transition(field=status, source=[OrderStatus.DISPATCHED, OrderStatus.TRAVELLING, OrderStatus.OUT_FOR_DELIVERY_GROCERY], target=OrderStatus.DELIVERED)
    def complete_order(self):
        self.actual_delivery_time = timezone.now()
    
    @transition(field=status, source='*', target=OrderStatus.CANCELLED)
    def cancel_order(self):
        pass
    
    def __str__(self):
        return f"Order {self.order_number} - {self.user_id.name if self.user_id else 'Unknown'}"


class OrderItems(models.Model):
    item_id = models.BigAutoField(primary_key=True)
    order_id = models.ForeignKey(Orders, on_delete=models.CASCADE, related_name='items', db_column='order_id')
    menu_item_id = models.BigIntegerField(null=True, blank=True, help_text="Reference to MenuItems.item_id")
    product_item_id = models.BigIntegerField(null=True, blank=True, help_text="Reference to productItems.item_id")
    
    # Historical snapshots for immutability
    item_name_snapshot = models.CharField(max_length=255, help_text="Item name at order time")
    quantity = models.PositiveIntegerField()
    unit_price_snapshot = models.DecimalField(max_digits=10, decimal_places=2, help_text="Item price at order time")
    total_price = models.DecimalField(max_digits=10, decimal_places=2)
    item_details_snapshot = models.JSONField(help_text="Complete item details at order time")
    
    # Customizations
    customizations = models.JSONField(default=list, blank=True, help_text="Item customizations")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'order_items'
    
    def save(self, *args, **kwargs):
        if not self.item_id:
            last_item = OrderItems.objects.order_by('-item_id').first()
            if last_item:
                self.item_id = last_item.item_id + 1
            else:
                self.item_id = 2001
        
        # Calculate total price
        self.total_price = self.unit_price_snapshot * self.quantity
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.item_name_snapshot} x {self.quantity}"


class WalletPoints(models.Model):
    class TransactionType(models.TextChoices):
        EARNED = 'earned', 'Earned'
        SPENT = 'spent', 'Spent'
        REFUNDED = 'refunded', 'Refunded'
        EXPIRED = 'expired', 'Expired'
        ADJUSTMENT = 'adjustment', 'Adjustment'
    
    wallet_id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    transaction_type = models.CharField(max_length=20, choices=TransactionType.choices)
    points = models.DecimalField(max_digits=10, decimal_places=2)
    balance_after = models.DecimalField(max_digits=10, decimal_places=2, help_text="Balance after this transaction")
    
    # Related transactions
    related_order = models.ForeignKey(Orders, on_delete=models.SET_NULL, null=True, blank=True, related_name='wallet_transactions')
    related_coupon_purchase = models.ForeignKey('CouponPurchases', on_delete=models.SET_NULL, null=True, blank=True)
    
    description = models.TextField(help_text="Human readable description")
    expires_at = models.DateTimeField(null=True, blank=True, help_text="When these points expire")
    is_expired = models.BooleanField(default=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'wallet_points'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.wallet_id:
            last_wallet = WalletPoints.objects.order_by('-wallet_id').first()
            if last_wallet:
                self.wallet_id = last_wallet.wallet_id + 1
            else:
                self.wallet_id = 3001
        super().save(*args, **kwargs)
    
    @classmethod
    def get_user_balance(cls, user_id):
        """Get current wallet balance for user"""
        latest_transaction = cls.objects.filter(user_id=user_id).order_by('-created_at').first()
        return latest_transaction.balance_after if latest_transaction else Decimal('0.00')
    
    @classmethod
    def atomic_transaction(cls, user_id, points, transaction_type, description, related_order=None, related_coupon_purchase=None, expires_at=None):
        """Atomic wallet transaction with balance validation"""
        with transaction.atomic():
            # Get current balance
            current_balance = cls.get_user_balance(user_id)
            
            # Validate transaction
            if transaction_type == cls.TransactionType.SPENT and current_balance < points:
                raise ValueError(f"Insufficient balance. Available: {current_balance}, Required: {points}")
            
            # Calculate new balance
            if transaction_type in [cls.TransactionType.EARNED, cls.TransactionType.REFUNDED, cls.TransactionType.ADJUSTMENT]:
                new_balance = current_balance + points
            else:  # SPENT, EXPIRED
                new_balance = current_balance - points
            
            # Create transaction record
            wallet_transaction = cls.objects.create(
                user_id=user_id,
                transaction_type=transaction_type,
                points=points,
                balance_after=new_balance,
                related_order=related_order,
                related_coupon_purchase=related_coupon_purchase,
                description=description,
                expires_at=expires_at
            )
            
            return wallet_transaction
    
    def __str__(self):
        return f"{self.transaction_type} {self.points} points - {self.user_id.name if self.user_id else 'Unknown'}"


class Coupons(models.Model):
    class DiscountType(models.TextChoices):
        PERCENTAGE = 'percentage', 'Percentage'
        FIXED_AMOUNT = 'fixed_amount', 'Fixed Amount'
        FREE_DELIVERY = 'free_delivery', 'Free Delivery'
        BOGO = 'bogo', 'Buy One Get One'
    
    class CreatedBy(models.TextChoices):
        KIRAZEE_ADMIN = 'kirazee_admin', 'KiraZee Admin'
        BUSINESS_OWNER = 'business_owner', 'Business Owner'
    
    coupon_id = models.BigAutoField(primary_key=True)
    coupon_code = models.CharField(max_length=50, unique=True, db_index=True)
    discount_type = models.CharField(max_length=20, choices=DiscountType.choices)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    
    created_by = models.CharField(max_length=20, choices=CreatedBy.choices)
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, null=True, blank=True, to_field='business_id', db_column='business_id')
    
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    
    # Usage limits
    max_usage_total = models.PositiveIntegerField(null=True, blank=True, help_text="Total usage limit across all users")
    max_usage_per_user = models.PositiveIntegerField(default=1, help_text="Usage limit per user")
    current_usage_count = models.PositiveIntegerField(default=0)
    
    # Points requirement for purchase
    points_required = models.PositiveIntegerField(default=0, help_text="Points required to purchase this coupon")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'coupons'
        ordering = ['-created_at']
    
    def save(self, *args, **kwargs):
        if not self.coupon_id:
            last_coupon = Coupons.objects.order_by('-coupon_id').first()
            if last_coupon:
                self.coupon_id = last_coupon.coupon_id + 1
            else:
                self.coupon_id = 4001
        super().save(*args, **kwargs)
    
    def is_valid_for_user(self, user_id):
        """Check if coupon is valid for specific user"""
        # Check if coupon is active and within validity period
        if not self.is_active:
            return False, "Coupon is not active"
        
        now = timezone.now()
        if now < self.valid_from or now > self.valid_to:
            return False, "Coupon has expired"
        
        # Check total usage limit
        if self.max_usage_total and self.current_usage_count >= self.max_usage_total:
            return False, "Coupon usage limit exceeded"
        
        # Check per-user usage limit
        user_usage_count = CouponRedemptions.objects.filter(
            coupon_id=self,
            user_id=user_id
        ).count()
        
        if user_usage_count >= self.max_usage_per_user:
            return False, "You have already used this coupon"
        
        return True, "Coupon is valid"
    
    def __str__(self):
        return f"{self.coupon_code} - {self.discount_value}{'%' if self.discount_type == 'percentage' else ''} OFF"


class CouponRules(models.Model):
    class RuleType(models.TextChoices):
        MIN_CART_VALUE = 'min_cart_value', 'Minimum Cart Value'
        ALLOWED_BUSINESS = 'allowed_business', 'Allowed Business'
        DELIVERY_ONLY = 'delivery_only', 'Delivery Only'
        FIRST_ORDER_ONLY = 'first_order_only', 'First Order Only'
        USER_GROUP = 'user_group', 'User Group'
        ORDER_TYPE = 'order_type', 'Order Type'
    
    rule_id = models.BigAutoField(primary_key=True)
    coupon_id = models.ForeignKey(Coupons, on_delete=models.CASCADE, related_name='rules', db_column='coupon_id', to_field='coupon_id')
    rule_type = models.CharField(max_length=30, choices=RuleType.choices)
    rule_value = models.JSONField(help_text="Rule configuration in JSON format")
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'coupon_rules'
    
    def save(self, *args, **kwargs):
        if not self.rule_id:
            last_rule = CouponRules.objects.order_by('-rule_id').first()
            if last_rule:
                self.rule_id = last_rule.rule_id + 1
            else:
                self.rule_id = 5001
        super().save(*args, **kwargs)
    
    def evaluate_rule(self, order_data):
        """Evaluate rule against order data"""
        if self.rule_type == self.RuleType.MIN_CART_VALUE:
            min_value = self.rule_value.get('min_value', 0)
            return order_data.get('cart_value', 0) >= min_value
        
        elif self.rule_type == self.RuleType.ALLOWED_BUSINESS:
            allowed_businesses = self.rule_value.get('business_ids', [])
            return order_data.get('business_id') in allowed_businesses
        
        elif self.rule_type == self.RuleType.DELIVERY_ONLY:
            return order_data.get('order_type') == 'delivery'
        
        elif self.rule_type == self.RuleType.FIRST_ORDER_ONLY:
            user_id = order_data.get('user_id')
            if user_id:
                return not Orders.objects.filter(user_id=user_id, status=Orders.OrderStatus.DELIVERED).exists()
            return False
        
        return True
    
    def __str__(self):
        return f"{self.coupon_id.coupon_code} - {self.rule_type}"


class CouponPurchases(models.Model):
    purchase_id = models.BigAutoField(primary_key=True)
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    coupon_id = models.ForeignKey(Coupons, on_delete=models.CASCADE, db_column='coupon_id', to_field='coupon_id')
    points_spent = models.PositiveIntegerField()
    
    purchased_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'coupon_purchases'
        unique_together = ['user_id', 'coupon_id']
    
    def save(self, *args, **kwargs):
        if not self.purchase_id:
            last_purchase = CouponPurchases.objects.order_by('-purchase_id').first()
            if last_purchase:
                self.purchase_id = last_purchase.purchase_id + 1
            else:
                self.purchase_id = 6001
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.user_id.name if self.user_id else 'Unknown'} purchased {self.coupon_id.coupon_code}"


class CouponRedemptions(models.Model):
    redemption_id = models.BigAutoField(primary_key=True)
    coupon_id = models.ForeignKey(Coupons, on_delete=models.CASCADE, db_column='coupon_id', to_field='coupon_id')
    order_id = models.ForeignKey(Orders, on_delete=models.CASCADE, db_column='order_id')
    user_id = models.ForeignKey('kirazee_app.Registration', on_delete=models.CASCADE, to_field='user_id', db_column='user_id')
    
    discount_amount_applied = models.DecimalField(max_digits=10, decimal_places=2)
    original_order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    final_order_amount = models.DecimalField(max_digits=10, decimal_places=2)
    
    redeemed_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'coupon_redemptions'
    
    def save(self, *args, **kwargs):
        if not self.redemption_id:
            last_redemption = CouponRedemptions.objects.order_by('-redemption_id').first()
            if last_redemption:
                self.redemption_id = last_redemption.redemption_id + 1
            else:
                self.redemption_id = 7001
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.coupon_id.coupon_code} redeemed in order {self.order_id.order_number}"


class DeliveryCharges(models.Model):
    delivery_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, to_field='business_id', db_column='business_id')
    
    base_charge = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('30.00'))
    distance_slabs = models.JSONField(default=list, help_text="Distance-based pricing slabs")
    free_delivery_above = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Free delivery threshold")
    max_charge = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Maximum delivery charge")
    max_delivery_distance = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Maximum delivery distance in km")
    
    # Peak hour pricing
    peak_hours_start = models.TimeField(null=True, blank=True)
    peak_hours_end = models.TimeField(null=True, blank=True)
    peak_hour_multiplier = models.DecimalField(max_digits=3, decimal_places=2, default=Decimal('1.00'))
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'delivery_charges'
        unique_together = ['business_id']
    
    def save(self, *args, **kwargs):
        if not self.delivery_id:
            last_delivery = DeliveryCharges.objects.order_by('-delivery_id').first()
            if last_delivery:
                self.delivery_id = last_delivery.delivery_id + 1
            else:
                self.delivery_id = 8001
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Delivery config for {self.business_id.businessName if self.business_id else 'Unknown'}"


class PointsConfiguration(models.Model):
    config_id = models.BigAutoField(primary_key=True)
    business_id = models.ForeignKey('kirazee_app.Business', on_delete=models.CASCADE, null=True, blank=True, to_field='business_id', db_column='business_id')
    
    # Points earning configuration
    points_per_rupee_spent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.00'), help_text="Points earned per rupee spent")
    points_per_rupee_value = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal('0.1000'), help_text="Rupee value per point (default: 10 points = 1 rupee)")
    
    min_order_value_for_points = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('100.00'))
    max_points_per_order = models.PositiveIntegerField(null=True, blank=True, help_text="Maximum points that can be earned per order")
    points_expiry_days = models.PositiveIntegerField(default=365, help_text="Days after which points expire")
    
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'points_configuration'
    
    def save(self, *args, **kwargs):
        if not self.config_id:
            last_config = PointsConfiguration.objects.order_by('-config_id').first()
            if last_config:
                self.config_id = last_config.config_id + 1
            else:
                self.config_id = 9001
        super().save(*args, **kwargs)
    
    def __str__(self):
        business_name = self.business_id.businessName if self.business_id else "Global"
        return f"Points config for {business_name}"