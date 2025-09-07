from pyexpat import model
from datetime import datetime
from rest_framework import serializers
from kirazee_app.models import BusinessFinancial, BusinessType, BusinessFeature, Business, Registration, BusinessMapping
from business.models import MenuItems, BOM, productItems
from consumer.models import MenuCart, Orders, OrderItems, WalletPoints, Coupons, CouponRules, CouponPurchases, CouponRedemptions, DeliveryCharges, PointsConfiguration

class BusinessSerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = '__all__'

    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        feature_ids = obj.business_features or []
        features = BusinessFeature.objects.filter(
            feature_id__in=feature_ids,
            status=True
        ).values_list("feature_id", "details")

        # make a mapping dict {feature_id: details}
        feature_map = dict(features)

        return [
            f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
            for fid in feature_ids
        ]

class BusinessnearbySerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()
    
    class Meta:
        model = Business
        fields = ['business_id', 'businessName', 'businessType', 'address', 'location', 'distance_km', 'business_features', 'latitude', 'longitude']
        read_only_fields = ['distance_km']
    
    def get_distance_km(self, obj):
        return obj.distance.km if hasattr(obj, 'distance') else None

    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        feature_ids = obj.business_features or []
        features = BusinessFeature.objects.filter(
            feature_id__in=feature_ids,
            status=True
        ).values_list("feature_id", "details")

        # make a mapping dict {feature_id: details}
        feature_map = dict(features)

        return [
            f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
            for fid in feature_ids
        ]

class MenuItemsSerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()
    item_image = serializers.SerializerMethodField()
    
    class Meta:
        model = MenuItems
        fields = [
            'item_id', 'item_name', 'description', 'item_image',
            'item_category', 'item_type', 'availability_timings', 'preparation_time',
            'quantity', 'original_cost', 'charges', 'selling_price',
            'business_features', 'is_active', 'status', 'created_at', 'updated_at'
        ]
    
    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        if hasattr(obj, 'business_id') and obj.business_id:
            feature_ids = obj.business_id.business_features or []
            features = BusinessFeature.objects.filter(
                feature_id__in=feature_ids,
                status=True
            ).values_list("feature_id", "details")

            # make a mapping dict {feature_id: details}
            feature_map = dict(features)

            return [
                f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
                for fid in feature_ids
            ]
        return []
    
    def get_item_image(self, obj):
        """Build absolute URL for item image"""
        request = self.context.get('request')
        if request and obj.item_image:
            return request.build_absolute_uri(f'/kirazee/{obj.item_image}')
        return None

class productItemsSerializer(serializers.ModelSerializer):
    business_features = serializers.SerializerMethodField()
    item_image = serializers.SerializerMethodField()
    
    class Meta:
        model = productItems
        fields = [
            'item_id', 'item_name', 'item_image', 'item_type', 'material', 'gender', 'color',
            'item_category', 'description', 'is_organic', 'availability_timings', 'weight',
            'size', 'unit', 'rating', 'original_cost', 'gst', 'charges', 'selling_price',
            'wallet_points_availablity', 'wallet_points', 'mfg_data', 'expiry_date', 'stock',
            'business_features', 'is_active', 'status', 'created_at', 'updated_at'
        ]
    
    def get_business_features(self, obj):
        """
        Fetch feature details from DB for the feature_ids stored in Business.business_features
        and return them in the format: 'FEA01 - Feature_Name'
        """
        if hasattr(obj, 'business_id') and obj.business_id:
            feature_ids = obj.business_id.business_features or []
            features = BusinessFeature.objects.filter(
                feature_id__in=feature_ids,
                status=True
            ).values_list("feature_id", "details")

            # make a mapping dict {feature_id: details}
            feature_map = dict(features)

            return [
                f"{fid} - {feature_map.get(fid, 'Unknown_Feature')}"
                for fid in feature_ids
            ]
        return []
    
    def get_item_image(self, obj):
        """Build absolute URL for item image"""
        request = self.context.get('request')
        if request and obj.item_image:
            return request.build_absolute_uri(f'/kirazee/{obj.item_image}')
        return None

class MenuCartSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuCart
        fields = "__all__"


class OrderSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(read_only=True)
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    user_name = serializers.CharField(source='user_id.name', read_only=True)
    
    class Meta:
        model = Orders
        fields = [
            'order_id', 'order_number', 'user_id', 'business_id', 'business_name', 'user_name',
            'order_type', 'status', 'total_amount', 'discount_amount', 'delivery_charges',
            'final_amount', 'delivery_address_snapshot', 'billing_address_snapshot',
            'delivery_address', 'coupon_code', 'wallet_points_used', 'estimated_delivery_time',
            'actual_delivery_time', 'created_at', 'updated_at'
        ]
        read_only_fields = ['order_id', 'order_number', 'created_at', 'updated_at']


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItems
        fields = [
            'item_id', 'order_id', 'menu_item_id', 'product_item_id', 'item_name_snapshot',
            'quantity', 'unit_price_snapshot', 'total_price', 'item_details_snapshot',
            'customizations', 'created_at'
        ]
        read_only_fields = ['item_id', 'created_at']


class OrderDetailSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(read_only=True)
    business_details = serializers.SerializerMethodField()
    user_details = serializers.SerializerMethodField()
    delivery_address_details = serializers.SerializerMethodField()
    available_transitions = serializers.SerializerMethodField()
    
    class Meta:
        model = Orders
        fields = [
            'order_id', 'order_number', 'user_id', 'business_id', 'business_details',
            'user_details', 'order_type', 'status', 'total_amount', 'discount_amount',
            'delivery_charges', 'final_amount', 'delivery_address_snapshot',
            'billing_address_snapshot', 'delivery_address_details', 'coupon_code',
            'wallet_points_used', 'estimated_delivery_time', 'actual_delivery_time',
            'available_transitions', 'created_at', 'updated_at'
        ]
    
    def get_business_details(self, obj):
        if obj.business_id:
            return {
                'business_id': obj.business_id.business_id,
                'business_name': obj.business_id.businessName,
                'business_type': obj.business_id.businessType,
                'address': obj.business_id.address,
                'business_number': obj.business_id.businessNumber,
                'contact_mobile': obj.business_id.contact_mobile,
                'contact_support': obj.business_id.contact_support
            }
        return None
    
    def get_user_details(self, obj):
        if obj.user_id:
            return {
                'user_id': obj.user_id.user_id,
                'first_name': obj.user_id.firstName,
                'last_name': obj.user_id.lastName,
                'mobile_number': obj.user_id.mobileNumber,
                'email': obj.user_id.emailID
            }
        return None
    
    def get_delivery_address_details(self, obj):
        if obj.delivery_address_snapshot:
            return obj.delivery_address_snapshot
        elif obj.delivery_address:
            return {
                'address_line_1': obj.delivery_address.address_line_1,
                'address_line_2': obj.delivery_address.address_line_2,
                'city': obj.delivery_address.city,
                'state': obj.delivery_address.state,
                'pincode': obj.delivery_address.pincode,
                'address_type': obj.delivery_address.address_type
            }
        return None
    
    def get_available_transitions(self, obj):
        transitions = []
        for transition in obj.get_available_status_transitions():
            transitions.append({
                'action': transition.name,
                'target_status': transition.target,
                'description': transition.name.replace('_', ' ').title()
            })
        return transitions


class OrderListSerializer(serializers.ModelSerializer):
    order_number = serializers.UUIDField(read_only=True)
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Orders
        fields = [
            'order_id', 'order_number', 'business_name', 'order_type', 'status',
            'status_display', 'total_amount', 'final_amount', 'created_at'
        ]


class WalletPointsSerializer(serializers.ModelSerializer):
    transaction_type_display = serializers.CharField(source='get_transaction_type_display', read_only=True)
    rupee_value = serializers.SerializerMethodField()
    
    class Meta:
        model = WalletPoints
        fields = [
            'wallet_id', 'user_id', 'transaction_type', 'transaction_type_display',
            'points', 'balance_after', 'rupee_value', 'related_order', 'related_coupon_purchase',
            'description', 'expires_at', 'is_expired', 'created_at'
        ]
        read_only_fields = ['wallet_id', 'balance_after', 'created_at']
    
    def get_rupee_value(self, obj):
        return float(obj.points * 0.10)  # 10 points = 1 rupee


class CouponSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    discount_display = serializers.SerializerMethodField()
    usage_remaining = serializers.SerializerMethodField()
    
    class Meta:
        model = Coupons
        fields = [
            'coupon_id', 'coupon_code', 'discount_type', 'discount_value', 'discount_display',
            'created_by', 'business_id', 'business_name', 'valid_from', 'valid_to',
            'is_active', 'max_usage_total', 'max_usage_per_user', 'current_usage_count',
            'usage_remaining', 'points_required', 'created_at', 'updated_at'
        ]
        read_only_fields = ['coupon_id', 'current_usage_count', 'created_at', 'updated_at']
    
    def get_discount_display(self, obj):
        if obj.discount_type == 'percentage':
            return f'{obj.discount_value}% OFF'
        elif obj.discount_type == 'fixed_amount':
            return f'₹{obj.discount_value} OFF'
        elif obj.discount_type == 'free_delivery':
            return 'FREE DELIVERY'
        elif obj.discount_type == 'bogo':
            return 'BUY 1 GET 1'
        return f'{obj.discount_value} OFF'
    
    def get_usage_remaining(self, obj):
        if obj.max_usage_total:
            return max(0, obj.max_usage_total - obj.current_usage_count)
        return None


class CouponRulesSerializer(serializers.ModelSerializer):
    class Meta:
        model = CouponRules
        fields = [
            'rule_id', 'coupon_id', 'rule_type', 'rule_value', 'is_active', 'created_at'
        ]
        read_only_fields = ['rule_id', 'created_at']


class CouponPurchaseSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source='coupon_id.coupon_code', read_only=True)
    user_name = serializers.CharField(source='user_id.name', read_only=True)
    
    class Meta:
        model = CouponPurchases
        fields = [
            'purchase_id', 'user_id', 'user_name', 'coupon_id', 'coupon_code',
            'points_spent', 'purchased_at'
        ]
        read_only_fields = ['purchase_id', 'purchased_at']


class CouponRedemptionSerializer(serializers.ModelSerializer):
    coupon_code = serializers.CharField(source='coupon_id.coupon_code', read_only=True)
    order_number = serializers.UUIDField(source='order_id.order_number', read_only=True)
    user_name = serializers.CharField(source='user_id.name', read_only=True)
    
    class Meta:
        model = CouponRedemptions
        fields = [
            'redemption_id', 'coupon_id', 'coupon_code', 'order_id', 'order_number',
            'user_id', 'user_name', 'discount_amount_applied', 'original_order_amount',
            'final_order_amount', 'redeemed_at'
        ]
        read_only_fields = ['redemption_id', 'redeemed_at']


class DeliveryChargesSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    
    class Meta:
        model = DeliveryCharges
        fields = [
            'delivery_id', 'business_id', 'business_name', 'base_charge', 'distance_slabs',
            'free_delivery_above', 'max_charge', 'max_delivery_distance', 'peak_hours_start',
            'peak_hours_end', 'peak_hour_multiplier', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['delivery_id', 'created_at', 'updated_at']


class PointsConfigurationSerializer(serializers.ModelSerializer):
    business_name = serializers.CharField(source='business_id.businessName', read_only=True)
    
    class Meta:
        model = PointsConfiguration
        fields = [
            'config_id', 'business_id', 'business_name', 'points_per_rupee_spent',
            'points_per_rupee_value', 'min_order_value_for_points', 'max_points_per_order',
            'points_expiry_days', 'is_active', 'created_at', 'updated_at'
        ]
        read_only_fields = ['config_id', 'created_at', 'updated_at']
