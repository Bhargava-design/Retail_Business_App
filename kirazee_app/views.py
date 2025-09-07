# your_app/views.py
from django.db.models import Q
from django.db import connection
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import ValidationError
from django.db import transaction  # Import transaction
from django.utils import timezone
from datetime import timedelta
from django.conf import settings
import os
from PIL import Image
import json
from types import SimpleNamespace
from typing import Any, Optional
from .models import (
    Registration,
    Otp,
    UserAddress,
    Business,
    BusinessType,
    BusinessMapping,
    BusinessOwnerDetails,
    NavigationItem,
)
from .serializers import RegistrationSerializer, UserAddressSerializer, NavigationItemSerializer
from .utils import generate_otp, send_otp_email, send_otp_dual_channel

# Helper to build absolute profile URL with default fallback
def build_profile_url(request, user: Registration):
    base_url = request.build_absolute_uri('/')[:-1]
    # If user has a non-empty profileUrl, use it; otherwise fallback to default image
    path = getattr(user, 'profileUrl', None)
    if path:
        path = str(path).strip()
        if path:
            return f"{base_url}/kirazee/{path}"
    return f"{base_url}/kirazee/media/default_images/user.png"

def build_business_logo_url(request, logo: Business):
    base_url = request.build_absolute_uri('/')[:-1]
    # If user has a non-empty profileUrl, use it; otherwise fallback to default image
    path = getattr(logo, 'logo', None)
    if path:
        path = str(path).strip()
        if path:
            return f"{base_url}/kirazee/{path}"
    return f"{base_url}/kirazee/media/business_logos/default_logo.jpeg"

def build_business_banner_url(request, banner: Business):
    base_url = request.build_absolute_uri('/')[:-1]
    # If user has a non-empty profileUrl, use it; otherwise fallback to default image
    path = getattr(banner, 'banner', None)
    if path:
        path = str(path).strip()
        if path:
            return f"{base_url}/kirazee/{path}"
    return f"{base_url}/kirazee/media/business_banners/default_banners.jpg"

class RegistrationAPIView(APIView):
    @transaction.atomic  # Ensures all database operations succeed or none do
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobileNumber')
        email = request.data.get('emailID')

        unverified_user = Registration.objects.filter(mobileNumber=mobile, is_verified=False).first()

        if unverified_user and unverified_user.emailID != email:
            # SCENARIO: MISTYPED EMAIL FOUND.

            # THE FIX: First, delete the old OTP record linked to the mobile number.
            # This unlocks the parent 'registrations' record for updates.
            Otp.objects.filter(mobileNumber=unverified_user).delete()

            # Now, you can safely update the user's details, including the email.
            unverified_user.firstName = request.data.get('firstName', unverified_user.firstName)
            unverified_user.lastName = request.data.get('lastName', unverified_user.lastName)
            unverified_user.countryCode = request.data.get('countryCode', unverified_user.countryCode)
            unverified_user.emailID = email
            unverified_user.dob = request.data.get('dob', unverified_user.dob)
            unverified_user.tokenID = request.data.get('tokenID', unverified_user.tokenID)
            unverified_user.uuid = request.data.get('uuid', unverified_user.uuid)
            unverified_user.os = request.data.get('os', unverified_user.os)
            unverified_user.mobileNumber = request.data.get('mobileNumber', unverified_user.mobileNumber)
            unverified_user.save()
            registration = unverified_user

            # Finally, create a brand new OTP record linked to the mobile number.
            otp_code = generate_otp()
            # --- CORRECTED OTP CREATION FOR UPDATE ---
            Otp.objects.create(
                mobileNumber=registration,
                tokenID=registration.tokenID,
                emailID=registration.emailID,
                code=otp_code
            )
            # Send OTP via both Email and WhatsApp
            user_name = f"{registration.firstName} {registration.lastName}"
            send_results = send_otp_dual_channel(
                registration.emailID, 
                registration.mobileNumber, 
                otp_code, 
                "REGISTRATION_OTP", 
                user_name
            )
            print(f"OTP sending results for {registration.emailID}: {send_results}")
            # Return the success response
            response_data = {
                "status": "success",
                "otp_sent_status": 1,
                "message": "Registration updated successful. An OTP has been sent to your email and WhatsApp for verification.",
                "data": {
                    "user_id": registration.user_id,
                    "emailID": registration.emailID,
                    "user_mode": registration.user_mode
                }
            }
            return Response(response_data, status=status.HTTP_200_OK)

        # --- Fallback for all other cases (new user, etc.) ---
        try:
            serializer = RegistrationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            registration = serializer.save()

            otp_code = generate_otp()
            # This part now works correctly because the model is fixed
            Otp.objects.create(
                mobileNumber=registration,
                tokenID=registration.tokenID,
                emailID=registration.emailID,
                code=otp_code
            )
            # Send OTP via both Email and WhatsApp
            user_name = f"{registration.firstName} {registration.lastName}"
            send_results = send_otp_dual_channel(
                registration.emailID, 
                registration.mobileNumber, 
                otp_code, 
                "REGISTRATION_OTP", 
                user_name
            )
            print(f"OTP sending results for {registration.emailID}: {send_results}")
            response_data = {
                "status": "success",
                "otp_sent_status": 1,
                "message": "Registration successful. An OTP has been sent to your email and WhatsApp for verification.",
                "data": {
                    "user_id": registration.user_id,
                    "emailID": registration.emailID,
                    "user_mode": registration.user_mode
                }
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)

class OtpVerificationAPIView(APIView):
    """
    Verifies the OTP sent to a user.
    """
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobile')
        otp_code = request.data.get('otp')

        if not mobile or not otp_code:
            return Response(
                {"message": "Mobile number and OTP are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Step 1: Find the user by their mobile number
            user = Registration.objects.get(mobileNumber=mobile)

            # Handle case where user is already verified
            if user.is_verified:
                return Response({
                    "message": "User already verified.",
                    "verification_status": True
                }, status=status.HTTP_200_OK)

            # Step 2: Find the latest, unused OTP for this user
            latest_otp = Otp.objects.filter(mobileNumber=user, status=False).latest('created_at')

            # Step 3: Check if the OTP has expired (3-minute limit)
            if timezone.now() - latest_otp.updated_at > timedelta(minutes=3):
                return Response(
                    {"message": "OTP has expired. Please request a new one."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Step 4: Check if the submitted OTP is correct
            if latest_otp.code != otp_code:
                return Response(
                    {"message": "Invalid OTP. Please try again."},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # --- Verification Success ---
            # Step 5: Update user and OTP status
            user.is_verified = True
            user.save()

            latest_otp.status = True  # Mark this OTP as used
            latest_otp.save()

            # Step 6: Prepare the detailed success response
            user_details = {
                "user_id": user.user_id,
                "firstName": user.firstName,
                "lastName": user.lastName,
                "displayName": f"{user.firstName}{user.lastName}",
                "mobileNumber": user.mobileNumber,
                "emailID": user.emailID,
                "tokenID": user.tokenID,
                "dob": user.dob,
                "is_verified": user.is_verified,
                "is_active": user.is_active,
                "user_mode": user.user_mode,
                "status": user.status,
                "profileUrl": build_profile_url(request, user),
                "uuid": user.uuid,
                "os": user.os,
                "whichapp": user.whichapp,
                "created_at": user.created_at,
                "updated_at": user.updated_at
            }

            return Response({
                "verification_status": True,
                "message": "Verification Successfull",
                "user_details": user_details
            }, status=status.HTTP_200_OK)

        except Registration.DoesNotExist:
            return Response(
                {"message": f"User with mobile number {mobile} not found."},
                status=status.HTTP_404_NOT_FOUND
            )
        except Otp.DoesNotExist:
            # This occurs if no unused OTPs are found for the user
            return Response(
                {"message": "Invalid OTP or it has already been used. Please request a new one."},
                status=status.HTTP_404_NOT_FOUND
            )

class LoginAPIView(APIView):
    """
    Handles login for registered and verified users by sending an OTP.
    """
    @transaction.atomic
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobile')
        email = request.data.get('emailID')
        token_id = request.data.get('tokenID')
        uuid = request.data.get('uuid')

        if not mobile and not email:
            return Response(
                {"Message": "Mobile number or emailID is required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Find the user by either mobile or email
        user_query = Q()
        if mobile:
            user_query |= Q(mobileNumber=mobile)
        if email:
            user_query |= Q(emailID=email)

        user = Registration.objects.filter(user_query).first()

        # Case 1: User does not exist
        if not user:
            return Response(
                {"Message": "User not registered. Please register", "otp_sent_status": False},
                status=status.HTTP_404_NOT_FOUND
            )

        # Case 2: User account is deactivated (status=0)
        if not user.status:
            return Response(
                {"Message": "User not found..!"},
                status=status.HTTP_404_NOT_FOUND
            )

        # Case 3: User exists but has not completed initial verification
        if not user.is_verified:
            return Response(
                {"Message": "User not registered yet. Please register first."},
                status=status.HTTP_403_FORBIDDEN
            )

        # Case 4: User is valid. Update device tokens and send OTP.
        user.tokenID = token_id
        user.uuid = uuid
        user.save()

        # --- MODIFIED OTP HANDLING LOGIC ---
        latest_otp = Otp.objects.filter(mobileNumber=user).order_by('-created_at').first()
        new_otp_code = generate_otp()
        user_name = f"{user.firstName} {user.lastName}"

        if latest_otp and not latest_otp.status:
            # If the latest OTP was never used (status=0), update it.
            latest_otp.code = new_otp_code
            # The 'updated_at' field will refresh automatically, resetting the timer.
            latest_otp.save()
            # Send OTP via both Email and WhatsApp
            send_results = send_otp_dual_channel(
                user.emailID, 
                user.mobileNumber, 
                new_otp_code, 
                "LOGIN_OTP", 
                user_name
            )
            print(f"--- UPDATED OTP for {user.emailID} is: {new_otp_code} ---")
            print(f"OTP sending results: {send_results}")
        else:
            # If no OTP exists or the last one was used (status=1), create a new one.
            Otp.objects.create(
                mobileNumber=user,
                tokenID=user.tokenID,
                emailID=user.emailID,
                code=new_otp_code
            )
            # Send OTP via both Email and WhatsApp
            # CORRECTED: Removed the auth_token from the call
            send_results = send_otp_dual_channel(
                user.emailID, 
                user.mobileNumber, 
                new_otp_code, 
                "LOGIN_OTP", 
                user_name
            )
            print(f"--- CREATED new OTP for {user.emailID} is: {new_otp_code} ---")
            print(f"OTP sending results: {send_results}")
        # --- END OF MODIFICATION ---

        if user.is_active:
            message = "OTP generated and sent to your registered email and WhatsApp. Informing that your account is logged in another device please logout"
        else:
            message = "OTP generated and sent to your registered email and WhatsApp."

        response_data = {
            "message": message,
            "otp_sent_status": True,
            "mobile": user.mobileNumber,
            "emailID": user.emailID,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "user_mode": user.user_mode,
        }
        return Response(response_data, status=status.HTTP_200_OK)

class VerifyLoginOtpAPIView(APIView):
    """
    Verifies the OTP for a login attempt and activates the user session.
    """
    def post(self, request, *args, **kwargs):
        mobile = request.data.get('mobile')
        email = request.data.get('emailID')
        otp_code = request.data.get('otp')

        if not (mobile or email) or not otp_code:
            return Response({"message": "Mobile/Email and OTP are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Find the user by either mobile or email
        user_query = Q()
        if mobile:
            user_query |= Q(mobileNumber=mobile)
        if email:
            user_query |= Q(emailID=email)
            
        user = Registration.objects.filter(user_query).first()

        if not user:
            return Response({"message": "User not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            latest_otp = Otp.objects.filter(mobileNumber=user, status=False).latest('created_at')
        except Otp.DoesNotExist:
            return Response({"message": "Invalid OTP or it has already been used."}, status=status.HTTP_400_BAD_REQUEST)

        # Check for OTP expiration
        if timezone.now() - latest_otp.updated_at > timedelta(minutes=3):
            return Response({"message": "OTP has expired. Please request a new one."}, status=status.HTTP_400_BAD_REQUEST)

        # Check if OTP code is correct
        if latest_otp.code != otp_code:
            return Response({"message": "Invalid OTP. Please try again."}, status=status.HTTP_400_BAD_REQUEST)

        # --- Success: Activate user and complete login ---
        user.is_active = True
        user.save()

        latest_otp.status = True # Mark OTP as used
        latest_otp.save()

        user_details = {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "tokenID": user.tokenID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "user_mode": user.user_mode,
            "status": user.status,
            "profileUrl": build_profile_url(request, user),
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }
        
        return Response({
            "verification_status": True,
            "message": "Verification Successfull",
            "user_details": user_details
        }, status=status.HTTP_200_OK)

class LogoutAPIView(APIView):
    """
    Handles user logout by setting their account to inactive.
    Accepts riderID as a query parameter.
    """
    def get(self, request, *args, **kwargs):
        # Retrieve the riderID from the URL's query parameters
        rider_id = request.query_params.get('riderID')

        if not rider_id:
            return Response(
                {"message": "riderID is a required query parameter."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = Registration.objects.get(user_id=rider_id)

            # Case 1: If user is currently active, log them out.
            # This also handles the 'is_active: null' case as the condition will be false.
            if user.is_active:
                user.is_active = False
                user.save()
                return Response(
                    {"message": f"User {rider_id} has been successfully logged out.", "is_active": user.is_active},
                    status=status.HTTP_200_OK
                )
            # Case 2: If user is already inactive.
            else:
                return Response(
                    {"message": "User already logged out from the app."},
                    status=status.HTTP_200_OK
                )

        except Registration.DoesNotExist:
            return Response(
                {"message": f"User with riderID {rider_id} not found."},
                status=status.HTTP_404_NOT_FOUND
            )

class ChangeModeAPIView(APIView):
    """
    Changes the user's mode based on query param userID and body param mode_to.
    Expected URL: /change_mode?userID=<id>
    Expected body: { "mode_to": "retail business" }
    Allowed modes: consumer, retail_business, delivery_partner
    """
    def post(self, request, *args, **kwargs):
        # 1) Validate userID in query params
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        # 2) Normalize and validate target mode
        mode_to_raw = request.data.get('mode_to')
        if not mode_to_raw:
            return Response({"message": "mode is not defined"}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize input like "retail business" -> "retail_business", case-insensitive
        normalized = str(mode_to_raw).strip().lower().replace(" ", "_")
        allowed_modes = {"consumer", "retail_business", "delivery_partner"}
        if normalized not in allowed_modes:
            return Response({"message": "mode is not defined"}, status=status.HTTP_400_BAD_REQUEST)

        # 3) Find user by user_id
        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        # 4) If already in the target mode
        if user.user_mode == normalized:
            user_details = {
                "displayName": f"{user.firstName}{user.lastName}",
                "mobileNumber": user.mobileNumber,
                "emailID": user.emailID,
                "is_verified": user.is_verified,
                "is_active": user.is_active,
                "status": user.status,
                "profileUrl": build_profile_url(request, user),
                "tokenID": user.tokenID,
                "dob": user.dob,
                "uuid": user.uuid,
                "os": user.os,
                "whichapp": user.whichapp,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "user_id": user.user_id,
            }
            return Response({
                "message": f"Mode is already active in {normalized}",
                "current_mode": user.user_mode,
                "user_details": user_details
            }, status=status.HTTP_200_OK)

        # 5) Change mode and return success
        previous = user.user_mode
        user.user_mode = normalized
        user.save()

        user_details = {
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "status": user.status,
            "profileUrl": build_profile_url(request, user),
            "tokenID": user.tokenID,
            "dob": user.dob,
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "user_id": user.user_id,
        }
        return Response({
            "message": f"Mode changed to {normalized} successfully",
            "current_mode": user.user_mode,
            "user_details": user_details
        }, status=status.HTTP_200_OK)

class UpdateProfileAPIView(APIView):
    """
    Updates a user's profile fields based on userID query param.
    Also supports account deletion via a 'delete' flag in the body.

    URL: POST /update-profile?userID=<id>
    Body (form-data):
      - firstName (optional)
      - lastName (optional)
      - displayName (optional; generated by DB, cannot be set directly)
      - profileurl (optional; file)
      - delete (optional; true/false)
    """
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        # Disallow updates to these fields
        forbidden_fields = []
        for field in ["mobileNumber", "emailID"]:
            if field in request.data:
                forbidden_fields.append(field)
        if forbidden_fields:
            value = ", ".join(forbidden_fields)
            return Response({"message": f"You cannot update the {value}"}, status=status.HTTP_400_BAD_REQUEST)

        # Fetch user
        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        # Deletion is not handled via POST anymore. Use HTTP DELETE on this endpoint.
        if 'delete' in request.data:
            return Response({"message": "Use HTTP DELETE /update-profile?userID=<id> for account deletion (soft delete)."}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        # If account is soft-deleted (status=0), block profile updates
        if not bool(user.status):
            return Response({
                "message": "unable to update profile. account is deactivated"
            }, status=status.HTTP_403_FORBIDDEN)

        # Track if any update happened
        updated = False

        # Update firstName and lastName if provided
        first_name = request.data.get('firstName')
        last_name = request.data.get('lastName')
        display_name = request.data.get('displayName')  # Informational only; DB generated
        dob = request.data.get('dob')
        if first_name is not None:
            user.firstName = first_name
            updated = True
        if last_name is not None:
            user.lastName = last_name
            updated = True
        if dob is not None:
            user.dob = dob
            updated = True

        # Handle profile image upload
        file_obj = request.FILES.get('profileurl')
        if file_obj:
            # Build new filename: KIR<user_id><DDMMYYHRMMSS><orig_ext>
            timestamp = timezone.now().strftime('%d%m%y%H%M%S')
            orig_ext = os.path.splitext(file_obj.name)[1]
            # Default to .jpg if no extension provided
            ext = orig_ext if orig_ext else '.jpg'
            new_filename = f"KIR{user.user_id}{timestamp}{ext}"
            rel_dir = os.path.join('media', 'profiles')
            abs_dir = os.path.join(settings.BASE_DIR, rel_dir)
            os.makedirs(abs_dir, exist_ok=True)
            abs_path = os.path.join(abs_dir, new_filename)

            # Compress and save image: JPEG/WEBP -> quality=70, PNG -> optimize, others -> save as-is
            try:
                img = Image.open(file_obj)
                fmt = ext.lower().lstrip('.')
                pil_format = {
                    'jpg': 'JPEG',
                    'jpeg': 'JPEG',
                    'png': 'PNG',
                    'webp': 'WEBP',
                    'gif': 'GIF',
                    'bmp': 'BMP',
                    'tif': 'TIFF',
                    'tiff': 'TIFF',
                }.get(fmt, None)

                save_kwargs = {}
                if pil_format in ('JPEG', 'WEBP'):
                    # Ensure JPEG has no alpha
                    if pil_format == 'JPEG':
                        if img.mode in ("RGBA", "LA"):
                            background = Image.new("RGB", img.size, (255, 255, 255))
                            background.paste(img, mask=img.split()[-1])
                            img = background
                        elif img.mode != "RGB":
                            img = img.convert("RGB")
                    save_kwargs = {"quality": 70, "optimize": True}
                elif pil_format == 'PNG':
                    # PNG doesn't use quality; optimize reduces size
                    save_kwargs = {"optimize": True}

                if pil_format:
                    img.save(abs_path, format=pil_format, **save_kwargs)
                else:
                    # Unknown format, attempt to save with detected format
                    img.save(abs_path)
            except Exception:
                return Response({"message": "invalid image file"}, status=status.HTTP_400_BAD_REQUEST)

            # Store relative path as per requirement
            user.profileUrl = os.path.join(rel_dir, new_filename).replace('\\', '/')
            updated = True

        if updated:
            user.save()

        # Build response details
        base_url = request.build_absolute_uri('/')[:-1]  # Drop trailing slash
        details = {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "status": user.status,
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

        # Provide full profile URL if set
        details["profileUrl"] = build_profile_url(request, user)

        message = "profile update successfully" if updated else "no changes"
        return Response({"message": message, "details": details}, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        """
        Account deletion rules:
        1) If is_active == 0 => block deletion with message.
        2) If is_verified == 0 => permanently delete (hard delete).
        3) Else => soft delete (status=0, is_active=0).
        URL: DELETE /update-profile?userID=<id>
        """
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id doesnot exist"}, status=status.HTTP_404_NOT_FOUND)

        # 1) Block if not active (not logged-in for deletion)
        if not bool(user.is_active):
            return Response({
                "message": "unable to delete your account. you not logged in to delete the account"
            }, status=status.HTTP_403_FORBIDDEN)

        # 2) If not verified => permanently delete
        if not bool(user.is_verified):
            user.delete()
            return Response({
                "message": "account permanently deleted successfully"
            }, status=status.HTTP_200_OK)

        # 3) Otherwise => soft delete
        user.status = False
        user.is_active = False
        user.save()

        # Build confirmation details
        base_url = request.build_absolute_uri('/')[:-1]
        details = {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": int(user.is_active) if isinstance(user.is_active, bool) else user.is_active,
            "status": int(user.status) if isinstance(user.status, bool) else user.status,
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at
        }
        details["profileUrl"] = build_profile_url(request, user)

        return Response({
            "message": "account soft-deleted successfully",
            "user_details": details
        }, status=status.HTTP_200_OK)

class AddressAPIView(APIView):
    """
    Manage user addresses.
    - POST /address?userID=... : create or update (home/work singletons; other can be multiple with tag). Handles default switching.
    - PATCH /address?userID=...&&id=... : update specific address and optionally switch default.
    - DELETE /address?userID=...&&id=... : soft delete (status=0) an address.
    """

    def _user_details(self, request, user: Registration):
        return {
            "user_id": user.user_id,
            "firstName": user.firstName,
            "lastName": user.lastName,
            "displayName": f"{user.firstName}{user.lastName}",
            "mobileNumber": user.mobileNumber,
            "emailID": user.emailID,
            "dob": user.dob,
            "is_verified": user.is_verified,
            "is_active": user.is_active,
            "status": user.status,
            "profileUrl": build_profile_url(request, user),
            "uuid": user.uuid,
            "os": user.os,
            "whichapp": user.whichapp,
            "user_mode": user.user_mode,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    def _list_user_addresses(self, user: Registration):
        qs = UserAddress.objects.filter(user=user, status=True).order_by('-is_default', '-updated_at', '-created_at')
        return UserAddressSerializer(qs, many=True).data

    def _ensure_single_default(self, user: Registration, keep_id: Optional[int]):
        UserAddress.objects.filter(user=user, status=True).exclude(id=keep_id).update(is_default=False)

    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        if not user_id:
            return Response({"message": "user_id not found"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id not found"}, status=status.HTTP_404_NOT_FOUND)

        address_type = request.data.get('address_type')
        tag = request.data.get('tag')
        is_default = request.data.get('is_default', False)
        address_payload = request.data.get('address', {})
        
        # Validate address type
        if not address_type:
            return Response({"message": "address_type is required"}, status=status.HTTP_400_BAD_REQUEST)

        normalized_type = str(address_type).strip().lower()
        if normalized_type not in {"home", "work", "other"}:
            return Response({"message": "Invalid address_type. Allowed: home, work, other"}, status=status.HTTP_400_BAD_REQUEST)

        if normalized_type == 'other' and not tag:
            return Response({"message": "you mention \"other\" in \"address_type\" , Please mention the tag."}, status=status.HTTP_400_BAD_REQUEST)

        # Convert is_default to bool
        is_default = bool(int(is_default)) if str(is_default).isdigit() else False

        # Ensure address payload contains required fields
        required_fields = ['Door no', 'street', 'city/town', 'state', 'pincode', 'country']
        if not all(field in address_payload for field in required_fields):
            return Response({"message": f"Address must contain: {', '.join(required_fields)}"}, status=status.HTTP_400_BAD_REQUEST)

        # Add latitude/longitude if provided
        if 'latitude' not in address_payload:
            address_payload['latitude'] = None
        if 'longitude' not in address_payload:
            address_payload['longitude'] = None

        with transaction.atomic():
            # For home/work addresses, update existing or create new
            if normalized_type in ['home', 'work']:
                address, created = UserAddress.objects.update_or_create(
                    user=user,
                    address_type=normalized_type,
                    defaults={
                        'tag': None,
                        'address': address_payload,
                        'status': True
                    }
                )
            else:
                # For 'other' addresses, create new entry
                address = UserAddress.objects.create(
                    user=user,
                    address_type=normalized_type,
                    tag=tag,
                    address=address_payload,
                    status=True
                )

            # Handle default address
            if is_default:
                self._ensure_single_default(user, address.id)
                address.is_default = True
                address.save()

        serializer = UserAddressSerializer(address)
        return Response({
            "message": "Address updated successfully" if normalized_type in ['home', 'work'] else "Address created successfully",
            "user_address": self._list_user_addresses(user)
        }, status=status.HTTP_200_OK)

    def patch(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        addr_id = request.query_params.get('id')
        if not user_id:
            return Response({"message": "user_id not found"}, status=status.HTTP_400_BAD_REQUEST)
        if not addr_id:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            address_obj = UserAddress.objects.get(id=addr_id, user=user, status=True)
        except UserAddress.DoesNotExist:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_404_NOT_FOUND)

        address_type = request.data.get('address_type')
        tag = request.data.get('tag')
        is_default = request.data.get('is_default')
        address_payload = request.data.get('address')

        if address_type:
            normalized_type = str(address_type).strip().lower()
            if normalized_type not in {"home", "work", "other"}:
                return Response({"message": "Invalid address_type. Allowed: home, work, other"}, status=status.HTTP_400_BAD_REQUEST)
            address_obj.address_type = normalized_type
            if normalized_type == 'other' and not tag and address_obj.tag in (None, ''):
                return Response({"message": "you mention \"other\" in \"address_type\" , Please mention the tag."}, status=status.HTTP_400_BAD_REQUEST)

        if tag is not None:
            address_obj.tag = tag
        if address_payload is not None:
            address_obj.address = address_payload

        def to_bool(val):
            if val is None:
                return None
            if isinstance(val, bool):
                return val
            if isinstance(val, (int, float)):
                return bool(int(val))
            if isinstance(val, str):
                return val.strip() in {"1", "true", "True"}
            return None

        is_default_bool = to_bool(is_default)
        if is_default_bool is not None:
            if is_default_bool:
                # Make this the only default: clear others first, then set this one as default
                with transaction.atomic():
                    self._ensure_single_default(user, keep_id=address_obj.id)
                    address_obj.is_default = True
                    address_obj.save()
            else:
                address_obj.is_default = False
                address_obj.save()
        else:
            address_obj.save()

        # user_details = self._user_details(request, user)
        addresses = self._list_user_addresses(user)
        return Response({
            "message": "Address updated successfully",
            # "user_details": user_details,
            "user_address": addresses
        }, status=status.HTTP_200_OK)

    def delete(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        addr_id = request.query_params.get('id')
        if not user_id:
            return Response({"message": "user_id not found"}, status=status.HTTP_400_BAD_REQUEST)
        if not addr_id:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = Registration.objects.get(user_id=user_id)
        except Registration.DoesNotExist:
            return Response({"message": "user_id not found"}, status=status.HTTP_404_NOT_FOUND)

        try:
            address_obj = UserAddress.objects.get(id=addr_id, user=user, status=True)
        except UserAddress.DoesNotExist:
            return Response({"message": "address id not assigned with userID , Please mention the correct id."}, status=status.HTTP_404_NOT_FOUND)

        address_obj.status = False
        address_obj.is_default = False
        address_obj.save()

        addresses = self._list_user_addresses(user)
        return Response({
            "message": "Address deleted successfully",
            "user_address": addresses
        }, status=status.HTTP_200_OK)


class UserComprehensiveDetailsAPIView(APIView):
    """
    POST /user-comprehensive?userID={value}&whichapp=kirazee

    Modes supported based on user_mode column:
    - consumer: returns user_details, user_address
    - retail_business: returns user_details, user_address, bussiness_owner_details, user_business
    - delivery_partner: returns user_details, user_address

    Uses RAW SQL for all fetches as requested.
    """

    def _dictfetchall(self, cursor):
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

    def _dictfetchone(self, cursor):
        row = cursor.fetchone()
        if row is None:
            return None
        columns = [col[0] for col in cursor.description]
        return dict(zip(columns, row))

    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('userID')
        whichapp = request.query_params.get('whichapp')

        # Validate userID first
        if not user_id:
            return Response({"message": "userID not found"}, status=status.HTTP_400_BAD_REQUEST)

        # Optional check for whichapp parameter presence as per spec (case-insensitive match to "kirazee")
        # Not filtering by whichapp in DB, just acknowledging param.
        if whichapp is None:
            # Proceeding even if not provided, spec shows it in URL, but not mandated for logic.
            pass

        # 1) Fetch user_details from registrations
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM registrations
                WHERE user_id = %s
                LIMIT 1
                """,
                [user_id],
            )
            user_details = self._dictfetchone(cursor)

        # Ensure profileUrl is a full absolute URL with default fallback
        if user_details is not None:
            ns_user = SimpleNamespace(**user_details)
            user_details["profileUrl"] = build_profile_url(request, ns_user)

        if not user_details:
            # userID incorrect
            return Response({"message": "userID not found"}, status=status.HTTP_404_NOT_FOUND)

        # Get user_mode from user_details and normalize it
        user_mode = user_details.get('user_mode')
        mode_norm = (str(user_mode).strip().lower().replace(" ", "_") if user_mode else None)
        allowed = {"consumer", "retail_business", "retail_business_owner", "delivery_partner"}
        if mode_norm not in allowed:
            return Response({"message": "unable to recognize the user mode."}, status=status.HTTP_400_BAD_REQUEST)

        # 2) Fetch user_address from user_address (only active)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM user_address
                WHERE user_id = %s AND status = 1
                ORDER BY is_default DESC, updated_at DESC, created_at DESC
                """,
                [user_id],
            )
            user_address = self._dictfetchall(cursor)

        # Base payload
        payload = {
            "user_details": user_details,
            "user_address": user_address,
        }

        if mode_norm == "retail_business" or mode_norm == "retail_business_owner":
            # Check verification status for retail business users
            is_verified = user_details.get('is_verified', 0)
            verification_status_map = {
                0: "pending",
                1: "approved", 
                2: "rejected",
                3: "processing"
            }
            
            # Add verification status to user_details
            user_details["verification_status"] = verification_status_map.get(is_verified, "pending")
            
            # 3) Fetch user_bussiness_details from business_owner_details
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM business_owner_details
                    WHERE user_id = %s
                    LIMIT 1
                    """,
                    [user_id],
                )
                user_bussiness_details = self._dictfetchone(cursor)

            # 4) Identify user's business via business_mapping and fetch from businesses
            user_business = None
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT bm.business_id
                    FROM business_mapping bm
                    WHERE bm.user_id = %s AND bm.status = 1
                    LIMIT 1
                    """,
                    [user_id],
                )
                mapping = self._dictfetchone(cursor)

            if mapping and mapping.get("business_id"):
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT *
                        FROM businesses
                        WHERE business_id = %s
                        LIMIT 1
                        """,
                        [mapping["business_id"]],
                    )
                    user_business = self._dictfetchone(cursor)

            # Expand business_features from IDs to details mapping
            if user_business and user_business.get("business_features"):
                features_raw = user_business.get("business_features")
                try:
                    feature_ids = json.loads(features_raw) if isinstance(features_raw, str) else features_raw
                except Exception:
                    feature_ids = []
                if isinstance(feature_ids, list) and feature_ids:
                    # Fetch details for these feature IDs
                    placeholders = ",".join(["%s"] * len(feature_ids))
                    with connection.cursor() as cursor:
                        cursor.execute(
                            f"""
                            SELECT feature_id, details
                            FROM business_features
                            WHERE feature_id IN ({placeholders})
                            """,
                            feature_ids,
                        )
                        rows = cursor.fetchall()
                        # rows come as list of tuples; build map
                        available = {r[0]: r[1] for r in rows}
                    expanded = {fid: available.get(fid, "unknown") for fid in feature_ids}
                    user_business["business_features"] = expanded

            # Apply base URL presentation for logo and banner on main business
            if user_business is not None:
                ns = SimpleNamespace(**user_business)
                user_business["logo"] = build_business_logo_url(request, ns)
                user_business["banner"] = build_business_banner_url(request, ns)
                
                # Add verification status to business data
                business_is_verified = user_business.get('is_verified', 0)
                user_business["verification_status"] = verification_status_map.get(business_is_verified, "pending")
                
                # Add business type details from business_types table
                business_type_code = user_business.get("businessType")
                if business_type_code:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT code, type, categories
                            FROM business_types
                            WHERE code = %s
                            LIMIT 1
                            """,
                            [business_type_code],
                        )
                        business_type_details = self._dictfetchone(cursor)
                        if business_type_details:
                            user_business["businessTypeDetails"] = business_type_details

            # Attach sublevel businesses if this is a master business
            if user_business:
                level_val = str(user_business.get("level") or "").strip().lower()
                if level_val == "master":
                    sub_levels = []
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT *
                            FROM businesses
                            WHERE master = %s AND status = 1
                            ORDER BY created_at ASC
                            """,
                            [user_business.get("business_id")],
                        )
                        sub_rows = self._dictfetchall(cursor)

                    # For each sublevel, expand its business_features
                    for sb in sub_rows:
                        sb_features_raw = sb.get("business_features")
                        try:
                            sb_ids = json.loads(sb_features_raw) if isinstance(sb_features_raw, str) else sb_features_raw
                        except Exception:
                            sb_ids = []
                        if isinstance(sb_ids, list) and sb_ids:
                            placeholders = ",".join(["%s"] * len(sb_ids))
                            with connection.cursor() as cursor:
                                cursor.execute(
                                    f"""
                                    SELECT feature_id, details
                                    FROM business_features
                                    WHERE feature_id IN ({placeholders})
                                    """,
                                    sb_ids,
                                )
                                rows = cursor.fetchall()
                                available = {r[0]: r[1] for r in rows}
                            sb["business_features"] = {fid: available.get(fid, "unknown") for fid in sb_ids}
                        else:
                            sb["business_features"] = {}
                        # Apply base URL presentation for each sublevel logo/banner
                        sb_ns = SimpleNamespace(**sb)
                        sb["logo"] = build_business_logo_url(request, sb_ns)
                        sb["banner"] = build_business_banner_url(request, sb_ns)
                        
                        # Add verification status to sublevel business
                        sb_is_verified = sb.get('is_verified', 0)
                        sb["verification_status"] = verification_status_map.get(sb_is_verified, "pending")
                        
                        sub_levels.append(sb)

                    user_business["sub_level"] = sub_levels
                elif level_val == "sublevel":
                    master_id = user_business.get("master")
                    master_obj = None
                    if master_id:
                        with connection.cursor() as cursor:
                            cursor.execute(
                                """
                                SELECT *
                                FROM businesses
                                WHERE business_id = %s AND status = 1
                                LIMIT 1
                                """,
                                [master_id],
                            )
                            master_obj = self._dictfetchone(cursor)
                        # expand features for master too
                        if master_obj and master_obj.get("business_features"):
                            m_features_raw = master_obj.get("business_features")
                            try:
                                m_ids = json.loads(m_features_raw) if isinstance(m_features_raw, str) else m_features_raw
                            except Exception:
                                m_ids = []
                            if isinstance(m_ids, list) and m_ids:
                                placeholders = ",".join(["%s"] * len(m_ids))
                                with connection.cursor() as cursor:
                                    cursor.execute(
                                        f"""
                                        SELECT feature_id, details
                                        FROM business_features
                                        WHERE feature_id IN ({placeholders})
                                        """,
                                        m_ids,
                                    )
                                    rows = cursor.fetchall()
                                    available = {r[0]: r[1] for r in rows}
                                master_obj["business_features"] = {fid: available.get(fid, "unknown") for fid in m_ids}
                        # Apply base URL presentation for master logo/banner
                        if master_obj:
                            m_ns = SimpleNamespace(**master_obj)
                            master_obj["logo"] = build_business_logo_url(request, m_ns)
                            master_obj["banner"] = build_business_banner_url(request, m_ns)
                            
                            # Add verification status to master business
                            master_is_verified = master_obj.get('is_verified', 0)
                            master_obj["verification_status"] = verification_status_map.get(master_is_verified, "pending")
                            
                    user_business["sub_level"] = master_obj

            payload.update({
                "business_owner_details": user_bussiness_details,
                "user_business": user_business,
            })

        return Response(payload, status=status.HTTP_200_OK)


class NavigationAPIView(APIView):
    """
    GET /navigation?mode={mode}&category={category}&business_id={id}
    
    Returns navigation items based on user mode and current context.
    
    Examples:
    - /navigation?mode=consumer -> Main consumer navigation (home, categories, orders, profile)
    - /navigation?mode=consumer&category=restaurants -> Restaurant category navigation
    - /navigation?mode=consumer&category=restaurants&business_id=123 -> Restaurant menu navigation
    - /navigation?mode=consumer&category=groceries -> Grocery category navigation
    - /navigation?mode=consumer&category=groceries&business_id=456 -> Grocery products navigation
    """
    
    def get(self, request, *args, **kwargs):
        mode = request.query_params.get('mode', '').strip().lower()
        category = request.query_params.get('category', '').strip().lower()
        business_id = request.query_params.get('business_id', '').strip()
        business_type = request.query_params.get('type', '').strip().upper()
        
        # Validate mode
        if not mode:
            return Response({"message": "mode parameter is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        allowed_modes = {"consumer", "retail_business", "retail_business_owner", "delivery_partner"}
        if mode not in allowed_modes:
            return Response({"message": "Invalid mode. Allowed: consumer, retail_business, retail_business_owner, delivery_partner"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Build navigation based on context
        navigation_items = []
        
        if mode == "consumer":
            navigation_items = self._get_consumer_navigation(category, business_id)
        elif mode == "retail_business" or mode == "retail_business_owner":
            navigation_items = self._get_business_navigation(category, business_id, business_type)
        elif mode == "delivery_partner":
            # Future implementation for delivery partner mode
            navigation_items = self._get_delivery_navigation(category, business_id)
        
        return Response({
            "navigation": navigation_items
        }, status=status.HTTP_200_OK)
    
    def _get_consumer_navigation(self, category, business_id):
        """Get consumer mode navigation based on current context"""
        
        if not category:
            # Main consumer navigation: Home, Categories, Orders, Profile
            return self._get_navigation_items(['consumer_home', 'consumer_categories', 'consumer_orders', 'consumer_profile'])
        
        elif category == "restaurants" or category == "resturants":  # Handle typo in sample data
            if business_id:
                # Restaurant menu navigation: Back, Restaurants, Menu, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_restaurants', 
                    'consumer_menu',
                    'consumer_rewards_for res',
                    'consumer_cart_for_res'
                ])
            else:
                # Restaurant category navigation: Back, Restaurants, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_restaurants',
                    'consumer_rewards_for res', 
                    'consumer_cart_for_res'
                ])
        
        elif category == "groceries":
            if business_id:
                # Grocery products navigation: Back, Groceries, Products, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_groceries',
                    'consumer_products',
                    'consumer_rewards_for groc',
                    'consumer_cart_for_groc'
                ])
            else:
                # Grocery category navigation: Back, Groceries, Rewards, Cart
                return self._get_navigation_items([
                    'consumer_back_to_main',
                    'consumer_cat_groceries',
                    'consumer_rewards_for groc',
                    'consumer_cart_for_groc'
                ])
        
        else:
            # Unknown category, return main navigation
            return self._get_navigation_items(['consumer_home', 'consumer_categories', 'consumer_orders', 'consumer_profile'])
    
    def _get_business_navigation(self, category, business_id, business_type=None):
        """Get retail business mode navigation based on business type"""
        
        # For retail_business_owner mode with business type R02 (Restaurant)
        if business_type == "R02":
            return self._get_navigation_items([
                'rbo_dashboard',
                'rbo_purchases', 
                'rbo_inventory',
                'rbo_expenses',
                'rbo_orders',
                'rbo_sales',
                'rbo_reports',
                'rbo_staff',
                'rbo_supplier',
                'rbo_app_settings'
            ])
        
        # Default business navigation (can be extended for other business types)
        return []
    
    def _get_delivery_navigation(self, category, business_id):
        """Get delivery partner mode navigation - placeholder for future implementation"""
        return []
    
    def _get_navigation_items(self, item_ids):
        """Fetch navigation items by IDs and serialize them"""
        try:
            items = NavigationItem.objects.filter(
                id__in=item_ids,
                is_visible=True
            ).order_by('order', 'label')
            
            # Maintain the order specified in item_ids
            ordered_items = []
            for item_id in item_ids:
                item = items.filter(id=item_id).first()
                if item:
                    ordered_items.append(item)
            
            serializer = NavigationItemSerializer(ordered_items, many=True)
            return serializer.data
        except Exception as e:
            # Log error and return empty list
            print(f"Error fetching navigation items: {e}")
            return []
