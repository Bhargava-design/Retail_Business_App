from django.db.models.fields import return_None
from rest_framework.decorators import api_view
from rest_framework import status
from django.shortcuts import render
from django.http import JsonResponse
from django.conf import settings
from django.utils import timezone
import json
import razorpay
import logging
import pytz
from django.db import transaction
from rest_framework.response import Response
from rest_framework.views import csrf_exempt
from kirazee_app.models import Business, Registration
from .models import BusinessPayment
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags

# Configure logger
logger = logging.getLogger(__name__)

def get_ist_now():
    """Returns current time in IST (Asia/Kolkata)"""
    ist = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(ist)

def convert_to_ist(dt):
    """Converts any datetime to IST (Asia/Kolkata)"""
    if dt is None:
        return None
    ist = pytz.timezone('Asia/Kolkata')
    if timezone.is_aware(dt):
        return dt.astimezone(ist)
    return timezone.make_aware(dt, ist) 

@csrf_exempt
@transaction.atomic
def save_payment_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            transaction_id = data.get('transaction_id')
            amount = data.get('amount')
            status_param = data.get('status')
            business_id_str = data.get('business_id')
            user_id_str = data.get('user_id')
            
            # Initialize payment variables from request data
            payment_method_from_razorpay = data.get('payment_method')
            upi_id_from_razorpay = data.get('upi_id')

            payment_source_from_razorpay = None
            
            # Fetch payment details from Razorpay if transaction_id is present
            if transaction_id and transaction_id != 'no_txn_id' and status_param == 'success':
                client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
                try:
                    payment_details = client.payment.fetch(transaction_id)
                    payment_method_from_razorpay = payment_details.get('method')
                    upi_id_from_razorpay = payment_details.get('vpa') if payment_method_from_razorpay == 'upi' else None
                    status_param = payment_details.get('status') # Use the official status from Razorpay
                
                    # Extract payment source based on method
                    if payment_method_from_razorpay == 'upi':
                        if 'vpa' in payment_details:
                            # Define the dictionary and assign it to a variable
                            domain_mapping = {
                                "okicici": "Google Pay",
                                "okaxis": "Google Pay",
                                "oksbi": "Google Pay",
                                "okhdfc": "Google Pay",
                                "ybl": "PhonePe",
                                "ibl": "PhonePe",
                                "paytm": "Paytm",
                                "upi": "BHIM",
                                "apl": "Amazon Pay",
                                "cred": "Cred",
                                "wa": "WhatsApp Pay",
                                "airtel": "Airtel Payments Bank",
                                "kotak": "Kotak Mahindra Bank",
                                "axisbank": "Axis Bank",
                                "hdfcbank": "HDFC Bank",
                                "sbi": "State Bank of India",
                                "icici": "ICICI Bank"
                            }
                            # Extract the domain part of the VPA (e.g., 'paytm' from 'user@paytm')
                            vpa_domain = payment_details['vpa'].split('@')[-1]
                            payment_source_from_razorpay = domain_mapping.get(vpa_domain, vpa_domain)
                        else:
                            # Fallback if no VPA is available but method is UPI
                            payment_source_from_razorpay = payment_details.get('provider')
                    elif payment_method_from_razorpay == 'card':
                        payment_source_from_razorpay = payment_details.get('card', {}).get('issuer')
                    elif payment_method_from_razorpay == 'wallet':
                        payment_source_from_razorpay = payment_details.get('wallet')

                except Exception as e:
                    logger.error(f"Failed to fetch payment details from Razorpay for {transaction_id}: {e}") 
                    # Handle this as a verification failure to avoid saving inaccurate data
                    status_param = 'verification_failed'
            else:
                pass

            try:
                business_instance = Business.objects.get(business_id=business_id_str)
            except Business.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': f'Invalid businessID: {business_id_str}. Please use a valid businessID from Business table.'}, status=400)

            try:
                user_instance = Registration.objects.get(user_id=user_id_str)
            except Registration.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': f'Invalid userID: {user_id_str}. Please use a valid userID from Registration table.'}, status=400)

            # Get current time in IST
            current_time = get_ist_now()

            try:
                payment = BusinessPayment.objects.create(
                    transaction_id=transaction_id,
                    amount=amount,
                    currency='INR',
                    payment_method=payment_method_from_razorpay,
                    status=status_param,
                    upi_id=upi_id_from_razorpay,
                    payment_source=payment_source_from_razorpay,
                    business_id=business_instance,
                    user_id=user_instance,
                    created_at=current_time,
                    updated_at=current_time,
                    refund_status='Not Applicable',
                    refund_id='Not Applicable',
                    payment_type='Business'
                )

                # Update the business's payment status to 1 if payment was successful
                if status_param == 'captured' or status_param == 'authorized':
                    business_instance.paymentstatus = 1
                    business_instance.save(update_fields=['paymentstatus']) # Use update_fields for efficiency
                
                return JsonResponse({
                    'status': 'success',
                    'message': 'Payment data saved successfully!',
                    'payment': {
                        'transaction_id': payment.transaction_id,
                        'amount': float(payment.amount),
                        'payment_method': payment.payment_method,
                        'status': payment.status,
                        'upi_id': payment.upi_id,
                        'payment_source': payment.payment_source,
                        'business_id': str(payment.business_id.business_id),
                        'user_id': str(payment.user_id.user_id),
                        'created_at': convert_to_ist(payment.created_at).isoformat(),
                    }
                })
            except Exception as e:
                logger.error(f"Failed to create BusinessPayment record: {e}")
                return JsonResponse({'status': 'error', 'message': f'Failed to create payment record: {e}'}, status=500)
        except json.JSONDecodeError:
            return JsonResponse({'status': 'error', 'message': 'Invalid JSON data.'}, status=400)
    return JsonResponse({'status': 'error', 'message': 'Invalid request method.'}, status=405)

def send_refund_email(user_email, amount):
    """Sends a refund notification email to the user."""
    subject = 'Payment Refund Processed'
    html_message = render_to_string('refund_email_template.html', {'amount': amount})
    plain_message = strip_tags(html_message)
    from_email = settings.DEFAULT_FROM_EMAIL
    
    send_mail(subject, plain_message, from_email, [user_email], html_message=html_message)

@api_view(['POST'])
def process_refund(request):
    """
    Endpoint to process a refund and send an email notification.
    """
    if request.method == 'POST':
        transaction_id = request.data.get('transaction_id')
        amount = request.data.get('amount')

        if not transaction_id or not amount:
            return Response({"error": "Transaction ID and amount are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            payment_record = BusinessPayment.objects.get(transaction_id=transaction_id)
            user_email = payment_record.user_id.email
        except BusinessPayment.DoesNotExist:
            return Response({"error": "Payment record not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching payment record or user email: {e}")
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            refund_response = client.payment.refund(transaction_id, int(float(amount) * 100))
            
            # Update the payment record with refund status and ID
            payment_record.refund_status = refund_response['status']
            payment_record.refund_id = refund_response['id']
            payment_record.save()
            
            # Send email notification
            send_refund_email(user_email, amount)
            
            return Response({"message": "Refund processed and email sent", "refund_id": refund_response['id']}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(f"Razorpay refund failed for transaction {transaction_id}: {e}")
            return Response({"error": "Refund failed", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET']) # Changed to GET since parameters are in query params
def payment_gateway(request):
    if request.method == 'GET':
        user_id_str = request.query_params.get("userID")
        amount = request.query_params.get("amount")
        business_id_str = request.query_params.get("business_id")
        
        if not user_id_str:
            return Response({"error": "userID is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # We don't need to fetch the full user object, just validate its existence
            Registration.objects.get(user_id=user_id_str, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid user_id or user is not active."}, status=status.HTTP_404_NOT_FOUND)
        
        if not business_id_str:
            return Response({"error": "business_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            # We don't need to fetch the full business object, just validate its existence
            Business.objects.get(business_id=business_id_str, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id or business is not active."}, status=status.HTTP_404_NOT_FOUND)
        
        if not amount:
            return Response({"error": "amount is required"}, status=status.HTTP_400_BAD_REQUEST)

        context = {
            "user_id": user_id_str, # Pass the ID as a string
            "amount": amount,
            "business_id": business_id_str # Pass the ID as a string
        }
        return render(request, 'payment_gateway.html', context)
