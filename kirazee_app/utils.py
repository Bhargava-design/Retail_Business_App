import random
import smtplib
import requests
import json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from django.conf import settings
from .models import Registration

def generate_otp():
    """
    Generates a random 6-digit OTP.
    """
    return str(random.randint(100000, 999999))

def send_otp_email(email, otp_code, user_name="User"):
    """
    Send OTP via email using SMTP.
    """
    try:
        # Create message
        msg = MIMEMultipart()
        msg['From'] = settings.EMAIL_HOST_USER
        msg['To'] = email
        msg['Subject'] = "KiraZee - Your OTP Code"
        
        # Email body
        body = f"""
        Hi {user_name},
        
        Your OTP code for KiraZee is: {otp_code}
        
        This code will expire in 3 minutes.
        
        If you didn't request this code, please ignore this email.
        
        Best regards,
        KiraZee Team
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Create SMTP session
        server = smtplib.SMTP(settings.EMAIL_HOST, settings.EMAIL_PORT)
        server.starttls()  # Enable security
        server.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
        
        # Send email
        text = msg.as_string()
        server.sendmail(settings.EMAIL_HOST_USER, email, text)
        server.quit()
        
        print(f"OTP email sent successfully to {email}")
        return True
        
    except Exception as e:
        print(f"Failed to send OTP email to {email}: {str(e)}")
        return False

def send_whatsapp_otp(mobile_number, otp_code, template_type="LOGIN_OTP", user_name="User"):
    """
    Send OTP via WhatsApp using Interakt Messaging API.
    """
    try:
        # Get API configuration from settings
        base_url = settings.INTERAKT_API_BASE_URL
        api_key = settings.INTERAKT_API_KEY # Get the key from settings
        template_name = settings.WHATSAPP_TEMPLATES.get(template_type, 'kirazee_login_otp')
        
        # Prepare headers with the server-side API Key
        headers = {
            'Authorization': f'Basic {api_key}', # Use 'Basic' and the key from settings
            'Content-Type': 'application/json'
        }
        
        # Format mobile number
        phone_number = mobile_number.replace('+91', '').replace('+', '').strip()
        
        # Prepare payload
        payload = {
            "countryCode": "+91",
            "phoneNumber": phone_number,
            "callbackData": "some_callback_data",
            "type": "Template",
            "template": {
                "name": template_name,
                "languageCode": "en",
                "bodyValues": [user_name, otp_code]
            }
        }
        
        print(f"Sending WhatsApp OTP to +91{phone_number} with template {template_name}")
        
        # Make API call
        response = requests.post(base_url, headers=headers, json=payload, timeout=15)
        
        print(f"Response Status: {response.status_code}")
        print(f"Response Text: {response.text}")
        
        if response.status_code == 200 or response.status_code == 202:
            print(f"WhatsApp OTP sent successfully to +91{phone_number}")
            return True
        else:
            print(f"Failed to send WhatsApp OTP to +91{phone_number}. Status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"Error sending WhatsApp OTP: {str(e)}")
        return False
        
def send_otp_dual_channel(email, mobile_number, otp_code, template_type="LOGIN_OTP", user_name="User"):
    """
    Send OTP via both Email and WhatsApp channels.
    
    Args:
        email (str): Email address
        mobile_number (str): Mobile number
        otp_code (str): 6-digit OTP code
        template_type (str): "REGISTRATION_OTP" or "LOGIN_OTP"
        user_name (str): User's name
    
    Returns:
        dict: Status of both channels
    """
    results = {
        'email_sent': False,
        'whatsapp_sent': False,
        'at_least_one_sent': False
    }
    
    # Send via Email
    try:
        results['email_sent'] = send_otp_email(email, otp_code, user_name)
    except Exception as e:
        print(f"Email sending failed: {str(e)}")
        results['email_sent'] = False
    
    # Send via WhatsApp
    try:
        # CORRECTED: Call send_whatsapp_otp without the auth_token
        results['whatsapp_sent'] = send_whatsapp_otp(mobile_number, otp_code, template_type, user_name)
    except Exception as e:
        print(f"WhatsApp sending failed: {str(e)}")
        results['whatsapp_sent'] = False
    
    # Check if at least one channel succeeded
    results['at_least_one_sent'] = results['email_sent'] or results['whatsapp_sent']
    
    return results

def generate_user_id():
    """
    Generates a new unique user_id starting from 14771.
    It finds the latest user_id and increments it.
    """
    # Define the starting ID
    start_id = 14771
    
    # Find the last registration record by descending user_id
    last_registration = Registration.objects.order_by('-user_id').first()
    
    if last_registration and last_registration.user_id:
        # If a user exists, increment the last user_id
        new_id = last_registration.user_id + 1
        # Ensure the new ID is not smaller than the starting ID
        return max(new_id, start_id)
    else:
        # If no users exist, this is the first one
        return start_id
