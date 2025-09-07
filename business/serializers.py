# serializers.py
from pyexpat import model
from datetime import datetime
from rest_framework import serializers
from kirazee_app.models import BusinessFinancial, BusinessType, BusinessFeature, Business, Registration, BusinessMapping
from .models import MenuItems, BOM, productItems

class BusinessTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessType
        fields = ['type', 'code', 'categories']  # Only expose required fields

class BusinessFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessFeature
        fields = ['feature_id', 'details']

class Businesssection1serializers(serializers.ModelSerializer):
    logo_url = serializers.SerializerMethodField()
    banner_url = serializers.SerializerMethodField()

    class Meta:
        model = Business
        fields = [
            'businessName', 'businessType', 'businessCategory',
            'description', 'business_hours',
            'level', 'master',
            'businessEmail', 'businessNumber', 'businessWhatsapp',
            'logo_url', 'banner_url'
            ]

    def get_logo_url(self, obj):
        request = self.context.get("request")
        if request and obj.logo:
            return request.build_absolute_uri(obj.logo.url)
        return None

    def get_banner_url(self, obj):
        request = self.context.get("request")
        if request and obj.banner:
            return request.build_absolute_uri(obj.banner.url)
        return None

    def create(self, validated_data):
        user_id = self.context.get("user_id")

        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except:
            raise serializers.ValidationError("Invalid userID")

        # Default level = master if not provided
        level = validated_data.get("level", "master").lower()
        master = validated_data.get("master", None)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        # Master business
        if level == "master":
            business_id = f"KIR{user_id}{timestamp}"
            validated_data["master"] = None

        # Sublevel business
        elif level == "sublevel":
            if not master:
                raise serializers.ValidationError({"master": "Master business_id is required for sublevel"})
            if not Business.objects.filter(business_id=master, level="master").exists():
                raise serializers.ValidationError({"master": "Invalid master business_id"})
            business_id = f"KIR{user_id}{timestamp}"

        else:
            raise serializers.ValidationError({"level": "Invalid level. Must be 'master' or 'sublevel'"})

        validated_data["business_id"] = business_id

        # Pre-fill email/number from user if not mentioned
        if not validated_data.get("businessEmail"):
            validated_data["businessEmail"] = getattr(user, "email", None) or getattr(user, "mobileNumber", None)

        if not validated_data.get("businessNumber"):
            validated_data["businessNumber"] = getattr(user, "mobileNumber", None)

        # Whatsapp default = businessNumber
        if not validated_data.get("businessWhatsapp"):
            validated_data["businessWhatsapp"] = validated_data["businessNumber"]

        # Save business
        business = Business.objects.create(**validated_data)

        if level == "master":
            BusinessMapping.objects.create(user_id=user.user_id, business_id=business.business_id)

        return business

class Businesssection2Serializer(serializers.ModelSerializer):
    class Meta:
        model = Business
        fields = [
            'business_id', 'location', 'address',
            'landmark', 'city',
            'state', 'pincode',
            'contact_support', 'contact_mobile', 'website_url',
            'business_features', 'latitude', 'longitude'
            ]
    
    def update(self, instance, validated_data):
        # Update address & location fields
        instance.location = validated_data.get("location", instance.location)
        instance.address = validated_data.get("address", instance.address)
        instance.landmark = validated_data.get("landmark", instance.landmark)
        instance.city = validated_data.get("city", instance.city)
        instance.state = validated_data.get("state", instance.state)
        instance.pincode = validated_data.get("pincode", instance.pincode)
        instance.contact_support = validated_data.get("contact_support", instance.contact_support)
        instance.contact_mobile = validated_data.get("contact_mobile", instance.contact_mobile)
        instance.website_url = validated_data.get("website_url", instance.website_url)
        instance.business_features = validated_data.get("business_features", instance.business_features)
        instance.latitude = validated_data.get("latitude", instance.latitude)
        instance.longitude = validated_data.get("longitude", instance.longitude)

        instance.save()
        return instance

class Businesssection3Serializer(serializers.ModelSerializer):
    business_id = serializers.CharField(write_only=True)

    class Meta:
        model = BusinessFinancial
        # exclude the actual 'business' field from automatic validation
        exclude = ['business'] 

    def create(self, validated_data):
        business_id = validated_data.pop("business_id", None)

        if not business_id:
            raise serializers.ValidationError({"business_id": "This field is required."})

        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            raise serializers.ValidationError({"business_id": "Invalid business_id"})

        # Insert or update if business_id matches
        financial, created = BusinessFinancial.objects.update_or_create(
            business=business,
            defaults=validated_data
        )
        return financial

class MenuItemsSerializer(serializers.ModelSerializer):
    gst_percentage = serializers.DecimalField(max_digits=5, decimal_places=2, write_only=True, required=False, source='gst')
    
    class Meta:
        model = MenuItems
        fields = [
            'item_id', 'item_name', 'description','item_image',
            'item_category', 'item_type', 'availability_timings', 'preparation_time',
            'quantity', 'original_cost', 'gst_percentage', 'charges', 'selling_price',
            'is_active', 'status', 'created_at', 'updated_at'
        ]
        read_only_fields = ['item_id', 'charges', 'is_active', 'status', 'created_at', 'updated_at']
    
    def validate_selling_price(self, value):
        if value <= 0:
            raise serializers.ValidationError("Selling price must be greater than 0")
        return value
    
    def validate_availability_timings(self, value):
        if not value:
            return value
        
        # If it's a string, try to parse it as JSON
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Availability timings must be valid JSON")
        
        # Validate JSON structure
        if not isinstance(value, dict):
            raise serializers.ValidationError("Availability timings must be a JSON object")
        
        valid_days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        
        for day, timings in value.items():
            if day not in valid_days:
                raise serializers.ValidationError(f"Invalid day: {day}. Must be one of {valid_days}")
            
            if not isinstance(timings, list):
                raise serializers.ValidationError(f"Timings for {day} must be a list")
            
            for timing in timings:
                if not isinstance(timing, dict):
                    raise serializers.ValidationError(f"Each timing entry for {day} must be an object")
                
                if 'open' not in timing or 'close' not in timing:
                    raise serializers.ValidationError(f"Each timing entry must have 'open' and 'close' fields")
                
                # Validate time format (HH:MM)
                import re
                time_pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
                if not re.match(time_pattern, timing['open']) or not re.match(time_pattern, timing['close']):
                    raise serializers.ValidationError("Time format must be HH:MM (24-hour format)")
        
        return value
    
    def create(self, validated_data):
        # Calculate GST charges before saving
        if validated_data.get('original_cost') and validated_data.get('gst'):
            validated_data['charges'] = (validated_data['original_cost'] * validated_data['gst']) / 100
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Recalculate GST charges if original_cost or gst is updated
        if 'original_cost' in validated_data or 'gst' in validated_data:
            original_cost = validated_data.get('original_cost', instance.original_cost)
            gst = validated_data.get('gst', instance.gst)
            if original_cost and gst:
                validated_data['charges'] = (original_cost * gst) / 100
        
        return super().update(instance, validated_data)


class BOMSerializer(serializers.ModelSerializer):
    class Meta:
        model = BOM
        fields = ['bom_id', 'business_id', 'product_id', 'ingredients', 'quantity', 'unit', 'cost', 'status', 'created_at', 'updated_at']
        read_only_fields = ['bom_id', 'business_id', 'product_id', 'created_at', 'updated_at']

    def validate_cost(self, value):
        """Validate that cost is positive"""
        if value <= 0:
            raise serializers.ValidationError("Cost must be greater than 0")
        return value

    def validate_quantity(self, value):
        """Validate that quantity is positive"""
        if value <= 0:
            raise serializers.ValidationError("Quantity must be greater than 0")
        return value

    def validate_ingredients(self, value):
        """Validate that ingredients is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Ingredients cannot be empty")
        return value.strip()

    def validate_unit(self, value):
        """Validate that unit is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Unit cannot be empty")
        return value.strip()

class productItemsSerializer(serializers.ModelSerializer):
    class Meta:
        model = productItems
        fields = ['item_id', 'business_id', 'item_name', 'item_image', 'item_category', 'item_type', 'availability_timings', 'quantity', 'unit', 'rating', 'original_cost', 'gst', 'charges', 'selling_price', 'wallet_points_availablity', 'wallet_points', 'is_active', 'status', 'created_at', 'updated_at']
        read_only_fields = ['item_id', 'business_id', 'created_at', 'updated_at']
    
    def validate_selling_price(self, value):
            if value <= 0:
                raise serializers.ValidationError("Selling price must be greater than 0")
            return value
    
    def validate_wallet_points_availablity(self, value):
            # Convert to boolean if it's 0 or 1
            if value in [0, 1]:
                return bool(value)
            return value
    
    def validate_availability_timings(self, value):
        if not value:
            return value
        
        # If it's a string, try to parse it as JSON
        if isinstance(value, str):
            try:
                import json
                value = json.loads(value)
            except json.JSONDecodeError:
                raise serializers.ValidationError("Availability timings must be valid JSON")
        
        # Validate JSON structure
        if not isinstance(value, dict):
            raise serializers.ValidationError("Availability timings must be a JSON object")
        
        valid_days = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
        
        for day, timings in value.items():
            if day not in valid_days:
                raise serializers.ValidationError(f"Invalid day: {day}. Must be one of {valid_days}")
            
            if not isinstance(timings, list):
                raise serializers.ValidationError(f"Timings for {day} must be a list")
            
            for timing in timings:
                if not isinstance(timing, dict):
                    raise serializers.ValidationError(f"Each timing entry for {day} must be an object")
                
                if 'open' not in timing or 'close' not in timing:
                    raise serializers.ValidationError(f"Each timing entry must have 'open' and 'close' fields")
                
                # Validate time format (HH:MM)
                import re
                time_pattern = r'^([0-1]?[0-9]|2[0-3]):[0-5][0-9]$'
                if not re.match(time_pattern, timing['open']) or not re.match(time_pattern, timing['close']):
                    raise serializers.ValidationError("Time format must be HH:MM (24-hour format)")
        
        return value
    
    def create(self, validated_data):
        # Calculate GST charges before saving
        if validated_data.get('original_cost') and validated_data.get('gst'):
            validated_data['charges'] = (validated_data['original_cost'] * validated_data['gst']) / 100
        
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        # Recalculate GST charges if original_cost or gst is updated
        if 'original_cost' in validated_data or 'gst' in validated_data:
            original_cost = validated_data.get('original_cost', instance.original_cost)
            gst = validated_data.get('gst', instance.gst)
            if original_cost and gst:
                validated_data['charges'] = (original_cost * gst) / 100
        
        return super().update(instance, validated_data)