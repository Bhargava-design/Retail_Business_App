# your_app/urls.py

from django.urls import path
from .views import (
    RegistrationAPIView,
    OtpVerificationAPIView,
    LoginAPIView,
    VerifyLoginOtpAPIView,
    LogoutAPIView,
    ChangeModeAPIView,
    UpdateProfileAPIView,
    AddressAPIView,
    UserComprehensiveDetailsAPIView,
    NavigationAPIView
)

urlpatterns = [
    #Kirazee Account Management
    path('register/', RegistrationAPIView.as_view(), name='user-register'), # Register
    path('verify-otp/', OtpVerificationAPIView.as_view(), name='user-verify-otp'), # Verify OTP
    path('login/', LoginAPIView.as_view(), name='user-login'),     # Login
    path('verify-login-otp/', VerifyLoginOtpAPIView.as_view(), name='user-verify-login-otp'), # Verify Login OTP
    path('logout/', LogoutAPIView.as_view(), name='user-logout'),     # Logout
    path('change_mode', ChangeModeAPIView.as_view(), name='change-mode'),    # Change Mode
    path('update-profile', UpdateProfileAPIView.as_view(), name='update-profile'),    # Update profile / delete account
    path('address', AddressAPIView.as_view(), name='user-address'),    # Create/Update/Delete addresses
    path('user-comprehensive', UserComprehensiveDetailsAPIView.as_view(), name='user-comprehensive'),
    path('navigation', NavigationAPIView.as_view(), name='navigation'),    # Navigation items based on mode and category
]