from rest_framework import serializers
from .gro_models import Groceries, GroceriesCart, GroceriesOrders, GroceriesOrderItems, GroceriesPayments, GroceryPartner, GroceryDeliverDetails
from datetime import date
from django.db import transaction
import logging

logger = logging.getLogger(__name__)



class GroceriesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Groceries
        fields = '__all__'


class GroceriesCartSerializer(serializers.ModelSerializer):
    item = GroceriesSerializer(read_only=True)
    item_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = GroceriesCart
        fields = ['id', 'user', 'business', 'item', 'item_id', 'quantity', 'added_at', 'updated_at']
        read_only_fields = ['user', 'business']


class GroceriesPaymentsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GroceriesPayments
        fields = ['payment_method', 'payment_status', 'transaction_id', 'payment_date']


class GroceriesOrderItemsSerializer(serializers.ModelSerializer):
    item = GroceriesSerializer(read_only=True)

    class Meta:
        model = GroceriesOrderItems
        fields = ['item', 'quantity', 'unit_price', 'gst', 'total_price']


class GroceriesOrdersSerializer(serializers.ModelSerializer):
    order_items = GroceriesOrderItemsSerializer(many=True, read_only=True, source='groceriesorderitems_set')
    payments = GroceriesPaymentsSerializer(many=True, read_only=True, source='groceriespayments_set')

    class Meta:
        model = GroceriesOrders
        fields = [
            'order_id', 'user', 'business', 'order_type', 'order_status',
            'payment_status', 'total_amount', 'gst_amount', 'delivery_charge',
            'discount', 'final_amount', 'delivery_address', 'pickup_time',
            'created_at', 'updated_at', 'order_items', 'payments'
        ]


class OrderItemRequestSerializer(serializers.Serializer):
    item_id = serializers.IntegerField()
    quantity = serializers.IntegerField(min_value=1)


class CreateOrderSerializer(serializers.Serializer):
    order_type = serializers.ChoiceField(choices=GroceriesOrders.ORDER_TYPE_CHOICES)
    delivery_address = serializers.CharField(max_length=255, allow_blank=True, required=False)
    pickup_time = serializers.DateTimeField(required=False)
    delivery_charge = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)
    discount = serializers.DecimalField(max_digits=10, decimal_places=2, required=False, default=0.00)
    items = OrderItemRequestSerializer(many=True)

    def validate(self, data):
        if data.get('order_type') == 'delivery' and not data.get('delivery_address'):
            raise serializers.ValidationError("Delivery address is required for delivery orders.")
        if data.get('order_type') == 'pickup':
            if not data.get('pickup_time'):
                raise serializers.ValidationError("Pickup time is required for pickup orders.")
            if data.get('delivery_charge', 0.00) > 0:
                raise serializers.ValidationError("Delivery charge is not applicable for pickup orders.")
        if not data.get('items'):
            raise serializers.ValidationError("The items list cannot be empty.")
        return data




class CreatePaymentSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    payment_method = serializers.CharField(max_length=10)
    transaction_id = serializers.CharField(max_length=255, required=False)


class RazorpayPaymentVerificationSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    razorpay_order_id = serializers.CharField(max_length=255)
    razorpay_payment_id = serializers.CharField(max_length=255)
    razorpay_signature = serializers.CharField(max_length=255, allow_blank=True)


class HighRatedProductsRequestSerializer(serializers.Serializer):
    business_id = serializers.IntegerField()


class GroceryPartnerSerializer(serializers.ModelSerializer):
    delivery_zones = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True,
        help_text="List of delivery area codes"
    )
    
    class Meta:
        model = GroceryPartner
        fields = [
            'id', 'user', 'business', 'vehicle_number', 'vehicle_type',
            'driving_license_number', 'aadhar_card_number', 'bank_account_number',
            'bank_ifsc_code', 'bank_account_holder_name', 'emergency_contact_name',
            'emergency_contact_phone', 'delivery_zones', 'current_latitude',
            'current_longitude', 'availability_status', 'rating_average',
            'total_deliveries', 'is_verified', 'is_active', 'joined_date',
            'last_active_at', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'user', 'business', 'rating_average', 'total_deliveries', 
                           'is_verified', 'created_at', 'updated_at', 'last_active_at']

    def validate_aadhar_card_number(self, value):
        """Validate Aadhar card number format"""
        if len(value) != 12 or not value.isdigit():
            raise serializers.ValidationError("Aadhar card number must be exactly 12 digits.")
        return value

    def validate_vehicle_number(self, value):
        """Validate vehicle number format"""
        if len(value) < 6:
            raise serializers.ValidationError("Vehicle number must be at least 6 characters long.")
        return value.upper()

    def validate_driving_license_number(self, value):
        """Validate driving license number format"""
        if len(value) < 10:
            raise serializers.ValidationError("Driving license number must be at least 10 characters long.")
        return value.upper()

    def validate_bank_ifsc_code(self, value):
        """Validate IFSC code format"""
        if value and len(value) != 11:
            raise serializers.ValidationError("IFSC code must be exactly 11 characters long.")
        return value.upper() if value else value

    def validate_emergency_contact_phone(self, value):
        """Validate emergency contact phone number"""
        if value and (len(value) < 10 or not value.isdigit()):
            raise serializers.ValidationError("Emergency contact phone must be at least 10 digits.")
        return value

    def create(self, validated_data):
        """Create a new grocery partner"""
        # Set joined_date to today if not provided
        if 'joined_date' not in validated_data:
            validated_data['joined_date'] = date.today()
        
        return super().create(validated_data)


class GroceryPartnerRegistrationSerializer(serializers.ModelSerializer):
    """Serializer specifically for partner registration form"""
    delivery_zones = serializers.ListField(
        child=serializers.CharField(max_length=50),
        required=False,
        allow_empty=True,
        help_text="List of delivery area codes"
    )
    
    class Meta:
        model = GroceryPartner
        fields = [
            'vehicle_number', 'vehicle_type', 'driving_license_number',
            'aadhar_card_number', 'bank_account_number', 'bank_ifsc_code',
            'bank_account_holder_name', 'emergency_contact_name',
            'emergency_contact_phone', 'delivery_zones'
        ]

    def validate_aadhar_card_number(self, value):
        """Validate Aadhar card number format"""
        if len(value) != 12 or not value.isdigit():
            raise serializers.ValidationError("Aadhar card number must be exactly 12 digits.")
        
        # Check if Aadhar number already exists
        if GroceryPartner.objects.filter(aadhar_card_number=value).exists():
            raise serializers.ValidationError("A partner with this Aadhar card number already exists.")
        
        return value

    def validate_vehicle_number(self, value):
        """Validate vehicle number format"""
        if len(value) < 6:
            raise serializers.ValidationError("Vehicle number must be at least 6 characters long.")
        
        # Check if vehicle number already exists
        vehicle_number = value.upper()
        if GroceryPartner.objects.filter(vehicle_number=vehicle_number).exists():
            raise serializers.ValidationError("A partner with this vehicle number already exists.")
        
        return vehicle_number

    def validate_driving_license_number(self, value):
        """Validate driving license number format"""
        if len(value) < 10:
            raise serializers.ValidationError("Driving license number must be at least 10 characters long.")
        
        # Check if license number already exists
        license_number = value.upper()
        if GroceryPartner.objects.filter(driving_license_number=license_number).exists():
            raise serializers.ValidationError("A partner with this driving license number already exists.")
        
        return license_number

    def validate_bank_ifsc_code(self, value):
        """Validate IFSC code format"""
        if value and len(value) != 11:
            raise serializers.ValidationError("IFSC code must be exactly 11 characters long.")
        return value.upper() if value else value

    def validate_emergency_contact_phone(self, value):
        """Validate emergency contact phone number"""
        if value and (len(value) < 10 or not value.isdigit()):
            raise serializers.ValidationError("Emergency contact phone must be at least 10 digits.")
        return value


class GroceryDeliverDetailsSerializer(serializers.ModelSerializer):
    """Serializer for delivery details with nested order and partner information"""
    order_details = GroceriesOrdersSerializer(source='order', read_only=True)
    partner_details = GroceryPartnerSerializer(source='partner', read_only=True)
    assigned_by_user_name = serializers.SerializerMethodField()
    
    class Meta:
        model = GroceryDeliverDetails
        fields = [
            'delivery_detail_id', 'order', 'partner', 'assigned_by_user',
            'assignment_status', 'assigned_at', 'delivered_at', 'delivery_otp',
            'otp_verified_at', 'is_active', 'created_at', 'updated_at',
            'order_details', 'partner_details', 'assigned_by_user_name'
        ]
        read_only_fields = [
            'delivery_detail_id', 'assigned_at', 'delivered_at', 'delivery_otp',
            'otp_verified_at', 'created_at', 'updated_at'
        ]

    def get_assigned_by_user_name(self, obj):
        """Get the full name of the user who assigned the order"""
        if obj.assigned_by_user:
            return f"{obj.assigned_by_user.first_name} {obj.assigned_by_user.last_name}".strip()
        return None


class AssignOrderToPartnerSerializer(serializers.Serializer):
    """Serializer for assigning orders to delivery partners"""
    order_id = serializers.IntegerField()
    partner_user_id = serializers.IntegerField()
    generate_otp = serializers.BooleanField(default=True)
    
    def validate_order_id(self, value):
        """Validate that the order exists and is eligible for assignment"""
        try:
            order = GroceriesOrders.objects.get(order_id=value)
        except GroceriesOrders.DoesNotExist:
            raise serializers.ValidationError("Order not found.")
        
        # Check if order is already assigned
        if GroceryDeliverDetails.objects.filter(order=order, is_active=True).exists():
            raise serializers.ValidationError("This order is already assigned to a delivery partner.")
        
        # Check if order is delivery type
        if order.order_type != 'delivery':
            raise serializers.ValidationError("Only delivery orders can be assigned to partners.")
        
        # Temporarily allow all order statuses for testing
        # if order.order_status not in ['confirmed', 'pending']:
        #     raise serializers.ValidationError("Order must be confirmed or pending to assign to a partner.")
        
        return value
    
    def validate_partner_user_id(self, value):
        """Basic validation for partner_user_id - detailed validation in view"""
        if not value:
            raise serializers.ValidationError("Partner user ID is required.")
        return value
    
    def validate(self, data):
        """Cross-field validation"""
        order_id = data.get('order_id')
        partner_user_id = data.get('partner_user_id')
        
        if order_id and partner_user_id:
            # Additional business logic validation can be added here
            # For example, checking if partner serves the delivery area
            pass
        
        return data
    


class UpdateDeliveryStatusSerializer(serializers.Serializer):
    """Serializer for updating delivery status"""
    delivery_detail_id = serializers.IntegerField()
    new_status = serializers.ChoiceField(choices=GroceryDeliverDetails.ASSIGNMENT_STATUS_CHOICES)
    otp = serializers.CharField(max_length=6, required=False, allow_blank=True)
    
    def validate_delivery_detail_id(self, value):
        """Validate that the delivery detail exists"""
        try:
            delivery_detail = GroceryDeliverDetails.objects.get(delivery_detail_id=value, is_active=True)
        except GroceryDeliverDetails.DoesNotExist:
            raise serializers.ValidationError("Delivery assignment not found.")
        
        return value
    
    def validate(self, data):
        """Validate status transition and OTP if required"""
        delivery_detail_id = data.get('delivery_detail_id')
        new_status = data.get('new_status')
        otp = data.get('otp')
        
        if delivery_detail_id:
            try:
                delivery_detail = GroceryDeliverDetails.objects.get(delivery_detail_id=delivery_detail_id)
                
                # Check if status transition is valid
                if not delivery_detail.can_update_status(new_status):
                    raise serializers.ValidationError(
                        f"Cannot change status from {delivery_detail.assignment_status} to {new_status}"
                    )
                
                # Check OTP for delivered status
                if new_status == 'delivered':
                    if not otp:
                        raise serializers.ValidationError("OTP is required to mark delivery as completed.")
                    if not delivery_detail.verify_otp(otp):
                        raise serializers.ValidationError("Invalid OTP provided.")
                
            except GroceryDeliverDetails.DoesNotExist:
                pass  # Will be caught by field validation
        
        return data
    
    def update(self, instance, validated_data):
        """Update delivery status with business logic"""
        new_status = validated_data['new_status']
        
        try:
            with transaction.atomic():
                # Update status
                instance.assignment_status = new_status
                
                # Handle specific status changes
                if new_status == 'delivered':
                    instance.mark_delivered()
                    # Update partner status back to available
                    instance.partner.availability_status = 'available'
                    instance.partner.total_deliveries += 1
                    instance.partner.save(update_fields=['availability_status', 'total_deliveries'])
                    
                    # Update order status
                    instance.order.order_status = 'delivered'
                    instance.order.save(update_fields=['order_status'])
                    
                elif new_status == 'cancelled':
                    # Update partner status back to available
                    instance.partner.availability_status = 'available'
                    instance.partner.save(update_fields=['availability_status'])
                    
                    # Update order status
                    instance.order.order_status = 'cancelled'
                    instance.order.save(update_fields=['order_status'])
                
                instance.save()
                
                logger.info(f"Delivery {instance.delivery_detail_id} status updated to {new_status}")
                
                return instance
                
        except Exception as e:
            logger.error(f"Error updating delivery status: {str(e)}")
            raise serializers.ValidationError(f"Failed to update delivery status: {str(e)}")


class PartnerAssignedOrdersSerializer(serializers.Serializer):
    """Serializer for retrieving orders assigned to a specific partner"""
    partner_id = serializers.IntegerField()
    status_filter = serializers.ChoiceField(
        choices=GroceryDeliverDetails.ASSIGNMENT_STATUS_CHOICES,
        required=False,
        allow_blank=True
    )
    
    def validate_partner_id(self, value):
        """Validate that the partner exists"""
        try:
            GroceryPartner.objects.get(id=value)
        except GroceryPartner.DoesNotExist:
            raise serializers.ValidationError("Delivery partner not found.")
        
        return value


