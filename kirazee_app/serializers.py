from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from .models import Registration, UserAddress, NavigationItem
from .utils import generate_user_id

class RegistrationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Registration
        fields = [
            'firstName', 'lastName', 'countryCode', 'mobileNumber', 
            'emailID', 'dob', 'tokenID', 'uuid', 'os'
        ]

    def validate(self, data):
        """
        Custom validation to handle all registration scenarios and provide
        detailed error responses.
        """
        email = data.get('emailID')
        mobile = data.get('mobileNumber')

        # --- Part 1: Check for an existing user by EMAIL first ---
        existing_user_by_email = Registration.objects.filter(emailID=email).first()
        if existing_user_by_email:
            user_details = {
                "firstName": existing_user_by_email.firstName,
                "lastName": existing_user_by_email.lastName,
                "emailID": existing_user_by_email.emailID,
                "mobileNumber": existing_user_by_email.mobileNumber,
            }
            # If the user is already verified, it's a hard stop.
            if existing_user_by_email.is_verified:
                error_response = {
                    "emailID": ["This email is already registered and verified."],
                    "details": user_details
                }
                raise ValidationError(error_response)
            
            # If user is NOT verified, check for mistyped mobile scenario
            if existing_user_by_email.mobileNumber != mobile:
                raise ValidationError({
                    "status": "conflict", "code": "UNVERIFIED_ACCOUNT_EXISTS",
                    "message": "This email is tied to an unverified account with a different mobile. We will update it and resend the OTP.",
                })
            
            # If user is NOT verified and mobile is the SAME, it's a simple retry.
            # We still inform the user, as they need to verify.
            raise ValidationError({
                "emailID": ["This account already exists but has not been verified. An OTP will be resent."],
                "user_details": user_details
            })

        # --- Part 2: If no user by email, check by MOBILE ---
        existing_user_by_mobile = Registration.objects.filter(mobileNumber=mobile).first()
        if existing_user_by_mobile:
            # Since we already checked for email, any user found here MUST have a different email.
            # This covers the "mistyped email" scenario for both verified and unverified users.
            user_details = {
                "firstName": existing_user_by_mobile.firstName,
                "lastName": existing_user_by_mobile.lastName,
                "emailID": existing_user_by_mobile.emailID,
                "mobileNumber": existing_user_by_mobile.mobileNumber,
            }
            if existing_user_by_mobile.is_verified:
                raise ValidationError({
                    "mobileNumber": ["This mobile number is already registered and verified."],
                    "user_details": user_details
                })
            else: # Unverified user with a mistyped email
                raise ValidationError({
                    "status": "conflict", "code": "UNVERIFIED_ACCOUNT_EXISTS",
                    "message": "This mobile is tied to an unverified account with a different email. We will update it and resend the OTP.",
                })

        # If no user was found by email or mobile, it's a new registration.
        return data

    def create(self, validated_data):
        validated_data['user_id'] = generate_user_id()
        return Registration.objects.create(**validated_data)

    def update(self, instance, validated_data):
        instance.firstName = validated_data.get('firstName', instance.firstName)
        instance.lastName = validated_data.get('lastName', instance.lastName)
        instance.emailID = validated_data.get('emailID', instance.emailID)
        instance.mobileNumber = validated_data.get('mobileNumber', instance.mobileNumber)
        # ... update other fields ...
        instance.save()
        return instance


class UserAddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserAddress
        fields = [
            'id', 'user', 'address_type', 'tag', 'is_default', 'address', 'status',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'status', 'created_at', 'updated_at']

    def validate(self, attrs):
        address_type = attrs.get('address_type')
        tag = attrs.get('tag')
        if address_type:
            normalized = str(address_type).strip().lower()
            if normalized not in {'home', 'work', 'other'}:
                raise ValidationError({'address_type': ['Invalid type. Allowed: home, work, other']})
            if normalized == 'other' and not tag:
                raise ValidationError({'message': 'you mention "other" in "address_type" , Please mention the tag.'})
        return attrs


class NavigationItemSerializer(serializers.ModelSerializer):
    children = serializers.SerializerMethodField()
    
    class Meta:
        model = NavigationItem
        fields = ['label', 'icon_svg', 'order', 'is_visible', 
            'mode', 'route_path', 'parent', 'children'
        ]

    def get_children(self, obj):
        """Get child navigation items if any"""
        children = obj.children.filter(is_visible=True).order_by('order', 'label')
        if children.exists():
            return NavigationItemSerializer(children, many=True, context=self.context).data
        return []