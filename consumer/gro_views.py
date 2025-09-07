from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework import status
from django.db import connection
from .gro_models import Groceries, GroceryPartner, GroceryDeliverDetails
from .gro_serializers import (
    GroceriesSerializer, 
    GroceriesCartSerializer, 
    CreateOrderSerializer,
    GroceriesOrdersSerializer,
    CreatePaymentSerializer,
    GroceriesPaymentsSerializer,
    RazorpayPaymentVerificationSerializer,
    HighRatedProductsRequestSerializer,
    GroceryPartnerRegistrationSerializer,
    GroceryPartnerSerializer,
    GroceryDeliverDetailsSerializer,
    AssignOrderToPartnerSerializer,
    UpdateDeliveryStatusSerializer,
    PartnerAssignedOrdersSerializer
)
from .gro_models import GroceriesCart, GroceriesOrders, GroceriesOrderItems, GroceriesPayments
from kirazee_app.models import Registration, Business
from django.db import transaction
import razorpay
from django.conf import settings
from decimal import Decimal
import logging
from datetime import date

logger = logging.getLogger(__name__)



class GroceriesByBusinessView(APIView):
    """
    API view to fetch groceries by business ID using a raw SQL query.
    """
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch groceries for a given business ID from query parameters.
        """
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Use a raw SQL query to fetch data with alphabetical ordering
            groceries = Groceries.objects.raw(
                'SELECT * FROM `Groceries` WHERE business_id = %s AND is_active = TRUE AND status = TRUE ORDER BY item_name ASC',
                [business_id]
            )

            # Evaluate the RawQuerySet to check for results
            groceries_list = list(groceries)
            if not groceries_list:
                return Response({"message": "No groceries found for this business."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GroceriesSerializer(groceries_list, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroceryCategoriesByBusinessView(APIView):
    """
    API view to fetch distinct grocery categories by business ID.
    """
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch categories for a given business ID.
        """
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT DISTINCT item_category FROM `Groceries` WHERE business_id = %s AND item_category IS NOT NULL AND item_category != '' ORDER BY item_category ASC",
                    [business_id]
                )
                categories = [row[0] for row in cursor.fetchall()]

            if not categories:
                return Response({"message": "No categories found for this business."}, status=status.HTTP_404_NOT_FOUND)

            return Response({"categories": categories}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroceriesByCategoryView(APIView):
    """
    API view to fetch groceries grouped by category for a given business ID.
    """
    def get(self, request, *args, **kwargs):
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Get unique, non-empty categories for the business in alphabetical order
            categories = Groceries.objects.filter(
                business_id=business_id
            ).exclude(item_category__isnull=True).exclude(item_category__exact='').values_list('item_category', flat=True).distinct().order_by('item_category')

            if not categories:
                return Response({"message": "No categories found for this business."}, status=status.HTTP_404_NOT_FOUND)

            response_data = []
            for category in categories:
                # Get products for this category in alphabetical order by item_name
                products = Groceries.objects.filter(business_id=business_id, item_category=category).order_by('item_name')
                serializer = GroceriesSerializer(products, many=True)
                response_data.append({
                    "category": category,
                    "products": serializer.data
                })

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreateOrderView(APIView):
    """
    API view to create an order directly from a list of items.
    """
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')

        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        serializer = CreateOrderSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        items_data = serializer.validated_data['items']
        delivery_charge = Decimal(serializer.validated_data.get('delivery_charge', '0.00'))
        discount = Decimal(serializer.validated_data.get('discount', '0.00'))

        try:
            with transaction.atomic():
                total_amount = Decimal('0.00')
                gst_amount = Decimal('0.00')
                order_items_to_create = []

                for item_data in items_data:
                    try:
                        item = Groceries.objects.get(item_id=item_data['item_id'], business_id=business_id)
                    except Groceries.DoesNotExist:
                        return Response({"error": f"Item with id {item_data['item_id']} not found for this business."}, status=status.HTTP_404_NOT_FOUND)

                    quantity = item_data['quantity']
                    selling_price = item.selling_price or Decimal('0.00')
                    gst = item.gst or 0

                    total_price_for_item = selling_price * quantity
                    gst_for_item = (Decimal(gst) * total_price_for_item) / Decimal('100')

                    total_amount += total_price_for_item
                    gst_amount += gst_for_item

                    order_items_to_create.append(
                        GroceriesOrderItems(
                            item=item,
                            quantity=quantity,
                            unit_price=item.selling_price,
                            gst=item.gst,
                            total_price=total_price_for_item
                        )
                    )

                final_amount = total_amount + gst_amount + delivery_charge - discount

                order = GroceriesOrders.objects.create(
                    user_id=user_id,
                    business_id=business_id,
                    order_type=serializer.validated_data['order_type'],
                    delivery_address=serializer.validated_data.get('delivery_address'),
                    pickup_time=serializer.validated_data.get('pickup_time'),
                    total_amount=total_amount,
                    gst_amount=gst_amount,
                    delivery_charge=delivery_charge,
                    discount=discount,
                    final_amount=final_amount,
                )

                for order_item in order_items_to_create:
                    order_item.order = order
                
                GroceriesOrderItems.objects.bulk_create(order_items_to_create)

            order_serializer = GroceriesOrdersSerializer(order)
            return Response({"message": "Order created successfully.", "order": order_serializer.data}, status=status.HTTP_201_CREATED)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroceriesCartView(APIView):
    """
    API view for managing the user's grocery cart using query parameters.
    Supports adding, viewing, updating, and deleting cart items.
    """
    def get(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        cart_items = GroceriesCart.objects.filter(user_id=user_id, business_id=business_id).order_by('-added_at')
        serializer = GroceriesCartSerializer(cart_items, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        item_id = request.data.get('item_id')
        quantity = int(request.data.get('quantity', 1))

        if not all([user_id, business_id, item_id]):
            return Response({"error": "user_id, business_id, and item_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item, created = GroceriesCart.objects.get_or_create(
                user_id=user_id, business_id=business_id, item_id=item_id,
                defaults={'quantity': quantity}
            )
            if not created:
                cart_item.quantity += quantity
                cart_item.save()
            
            message = f"'{cart_item.item.item_name}' has been added to your cart." if created else f"'{cart_item.item.item_name}' quantity has been updated."
            serializer = GroceriesCartSerializer(cart_item)
            response_data = {
                "message": message,
                "data": serializer.data
            }
            return Response(response_data, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def patch(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        item_id = request.query_params.get('item_id')
        action = request.data.get('action')

        if not all([user_id, business_id, item_id, action]):
            return Response({"error": "user_id, business_id, item_id, and action are required."}, status=status.HTTP_400_BAD_REQUEST)

        if action not in ['increase', 'decrease']:
            return Response({"error": "Invalid action. Must be 'increase' or 'decrease'."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = GroceriesCart.objects.get(user_id=user_id, business_id=business_id, item_id=item_id)
            item_name = cart_item.item.item_name
            if action == 'increase':
                cart_item.quantity += 1
                cart_item.save()
                message = f"'{item_name}' quantity increased to {cart_item.quantity}."
            elif action == 'decrease':
                if cart_item.quantity > 1:
                    cart_item.quantity -= 1
                    cart_item.save()
                    message = f"'{item_name}' quantity decreased to {cart_item.quantity}."
                else:
                    cart_item.delete()
                    return Response({"message": f"'{item_name}' has been removed from your cart."}, status=status.HTTP_200_OK)
            
            serializer = GroceriesCartSerializer(cart_item)
            response_data = {
                "message": message,
                "data": serializer.data
            }
            return Response(response_data, status=status.HTTP_200_OK)
        except GroceriesCart.DoesNotExist:
            return Response({"error": "Item not found in cart."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def delete(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        item_id = request.query_params.get('item_id')

        if not all([user_id, business_id, item_id]):
            return Response({"error": "user_id, business_id, and item_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            cart_item = GroceriesCart.objects.get(user_id=user_id, business_id=business_id, item_id=item_id)
            item_name = cart_item.item.item_name
            cart_item.delete()
            return Response({"message": f"'{item_name}' has been removed from your cart."}, status=status.HTTP_200_OK)
        except GroceriesCart.DoesNotExist:
            return Response({"error": "Item not found in cart."}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CreatePaymentView(APIView):
    """
    API view to create a Razorpay order for a grocery payment.
    """
    def post(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')

        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required in query parameters."}, status=status.HTTP_400_BAD_REQUEST)

        order_id = request.data.get('order_id')
        if not order_id:
            return Response({"error": "order_id is required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            order = GroceriesOrders.objects.get(order_id=order_id, user_id=user_id, business_id=business_id)
        except GroceriesOrders.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        if order.payment_status == 'paid':
            return Response({"message": "This order has already been paid."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
            razorpay_order = client.order.create({
                "amount": int(order.final_amount * 100),  # Amount in paise
                "currency": "INR",
                "receipt": f"order_rcptid_{order.order_id}",
                "payment_capture": 1
            })


            response_data = {
                "message": "Razorpay order created successfully.",
                "razorpay_order_id": razorpay_order['id'],
                "amount": razorpay_order['amount'],
                "currency": razorpay_order['currency'],
                "key": settings.RAZORPAY_KEY_ID
            }
            return Response(response_data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating Razorpay order: {str(e)}")


class VerifyPaymentView(APIView):
    """
    API view to verify a Razorpay payment.
    """
    def post(self, request, *args, **kwargs):
        serializer = RazorpayPaymentVerificationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = serializer.validated_data
        razorpay_order_id = data['razorpay_order_id']
        razorpay_payment_id = data['razorpay_payment_id']
        razorpay_signature = data['razorpay_signature']

        try:
            order = GroceriesOrders.objects.get(order_id=request.data.get('order_id'))
        except GroceriesOrders.DoesNotExist:
            return Response({"error": "Order not found."}, status=status.HTTP_404_NOT_FOUND)

        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))

        try:
            client.utility.verify_payment_signature({
                'razorpay_order_id': razorpay_order_id,
                'razorpay_payment_id': razorpay_payment_id,
                'razorpay_signature': razorpay_signature
            })

            with transaction.atomic():
                payment = GroceriesPayments.objects.create(
                    order=order,
                    user_id=order.user_id,
                    amount=order.final_amount,
                    payment_method='razorpay',
                    payment_status='completed',
                    transaction_id=razorpay_payment_id
                )
                order.payment_status = 'paid'
                order.save()

            return Response({"message": "Payment verified and completed successfully."}, status=status.HTTP_200_OK)

        except razorpay.errors.SignatureVerificationError as e:
            logger.error(f"Razorpay signature verification failed: {e}")
            return Response({"error": "Payment verification failed."}, status=status.HTTP_400_BAD_REQUEST)


class OrderDetailsView(APIView):
    """
    API view to fetch order details based on user_id and business_id.
    Optionally filters by order_type if provided.
    """
    def get(self, request, *args, **kwargs):
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        order_type = request.query_params.get('order_type')

        if not all([user_id, business_id]):
            return Response({"error": "user_id and business_id are required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            filters = {
                'user_id': user_id,
                'business_id': business_id
            }
            if order_type:
                filters['order_type'] = order_type

            orders = GroceriesOrders.objects.filter(**filters).order_by('-created_at')

            if not orders.exists():
                return Response({"message": "No orders found for the given criteria."}, status=status.HTTP_404_NOT_FOUND)

            serializer = GroceriesOrdersSerializer(orders, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class HighRatedProductsView(APIView):
    """
    API view to fetch products with rating greater than 3 using raw SQL.
    Uses GET method with business_id as query parameter.
    """
    def get(self, request, *args, **kwargs):
        """
        Handles GET requests to fetch products with rating > 3 for a given business ID.
        """
        business_id = request.query_params.get('business_id')
        if not business_id:
            return Response({"error": "business_id parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Use raw SQL query to fetch products with rating > 3
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT item_id, business_id, item_name, item_image, item_type, material, 
                           gender, color, item_category, description, is_organic, 
                           availability_timings, weight, size, unit, rating, original_cost, 
                           gst, charges, selling_price, wallet_points_availablity, 
                           wallet_points, mfg_data, expiry_date, stock, is_active, 
                           status, created_at, updated_at
                    FROM Groceries 
                    WHERE business_id = %s 
                      AND rating > 3.0 
                      AND is_active = TRUE 
                      AND status = TRUE
                    ORDER BY rating DESC, item_name ASC LIMIT 10
                """, [business_id])
                
                columns = [col[0] for col in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]
            
            if not results:
                return Response({
                    "message": "No products found with rating greater than 3 for this business.",
                    "business_id": business_id,
                    "products": []
                }, status=status.HTTP_200_OK)
            
            # Convert the raw query results to match the serializer format
            products_data = []
            for result in results:
                # Convert any datetime fields to proper format
                if result['created_at']:
                    result['created_at'] = result['created_at'].isoformat()
                if result['updated_at']:
                    result['updated_at'] = result['updated_at'].isoformat()
                if result['availability_timings']:
                    result['availability_timings'] = str(result['availability_timings'])
                if result['mfg_data']:
                    result['mfg_data'] = result['mfg_data'].isoformat()
                if result['expiry_date']:
                    result['expiry_date'] = result['expiry_date'].isoformat()
                
                products_data.append(result)
            
            return Response({
                "message": f"Found {len(products_data)} products with rating greater than 3.",
                "business_id": business_id,
                "total_products": len(products_data),
                "products": products_data
            }, status=status.HTTP_200_OK)
            
        except Exception as e:
            logger.error(f"Error fetching high-rated products: {str(e)}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class GroceryPartnerRegistrationView(APIView):
    """
    API view for grocery partner registration.
    Handles partner registration with user_id and business_id from URL parameters.
    """
    
    def get(self, request, *args, **kwargs):
        """
        Get partner details if already registered, or return form structure.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Check if user exists
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
            
            # Check if partner already exists
            try:
                partner = GroceryPartner.objects.get(user_id=user_id)
                serializer = GroceryPartnerSerializer(partner)
                return Response({
                    "message": "Partner already registered.",
                    "partner_data": serializer.data,
                    "is_registered": True
                }, status=status.HTTP_200_OK)
            except GroceryPartner.DoesNotExist:
                # Return form structure for new registration
                return Response({
                    "message": "Partner not registered. Please fill the registration form.",
                    "is_registered": False,
                    "user_info": {
                        "user_id": user.user_id,
                        "name": f"{user.first_name} {user.last_name}",
                        "email": user.email,
                        "phone": user.phone_number
                    },
                    "business_info": {
                        "business_id": business.business_id,
                        "business_name": business.business_name
                    },
                    "form_fields": {
                        "vehicle_number": {"type": "text", "required": True, "max_length": 20},
                        "vehicle_type": {
                            "type": "select", 
                            "required": True,
                            "choices": [
                                {"value": "bike", "label": "Bike"},
                                {"value": "scooter", "label": "Scooter"},
                                {"value": "car", "label": "Car"},
                                {"value": "van", "label": "Van"},
                                {"value": "truck", "label": "Truck"},
                                {"value": "bicycle", "label": "Bicycle"},
                                {"value": "auto", "label": "Auto Rickshaw"}
                            ]
                        },
                        "driving_license_number": {"type": "text", "required": True, "max_length": 20},
                        "aadhar_card_number": {"type": "text", "required": True, "max_length": 12},
                        "bank_account_number": {"type": "text", "required": False, "max_length": 20},
                        "bank_ifsc_code": {"type": "text", "required": False, "max_length": 11},
                        "bank_account_holder_name": {"type": "text", "required": False, "max_length": 100},
                        "emergency_contact_name": {"type": "text", "required": False, "max_length": 100},
                        "emergency_contact_phone": {"type": "text", "required": False, "max_length": 15},
                        "delivery_zones": {"type": "array", "required": False, "description": "List of delivery area codes"}
                    }
                }, status=status.HTTP_200_OK)
                
        except Registration.DoesNotExist:
            return Response({
                "error": "User not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Business.DoesNotExist:
            return Response({
                "error": "Business not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in partner registration GET: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def post(self, request, *args, **kwargs):
        """
        Register a new grocery partner.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate user and business exist
            user = Registration.objects.get(user_id=user_id)
            business = Business.objects.get(business_id=business_id)
            
            # Check if partner already exists
            if GroceryPartner.objects.filter(user_id=user_id).exists():
                return Response({
                    "error": "Partner already registered for this user."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Validate form data
            serializer = GroceryPartnerRegistrationSerializer(data=request.data)
            if not serializer.is_valid():
                return Response({
                    "error": "Validation failed.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create partner with atomic transaction
            with transaction.atomic():
                partner_data = serializer.validated_data
                
                # Debug: Log the business object
                logger.info(f"Business object: {business}, Business ID: {business.business_id}")
                
                partner = GroceryPartner(
                    user=user,
                    business=business,
                    vehicle_number=partner_data['vehicle_number'],
                    vehicle_type=partner_data['vehicle_type'],
                    driving_license_number=partner_data['driving_license_number'],
                    aadhar_card_number=partner_data['aadhar_card_number'],
                    bank_account_number=partner_data.get('bank_account_number'),
                    bank_ifsc_code=partner_data.get('bank_ifsc_code'),
                    bank_account_holder_name=partner_data.get('bank_account_holder_name'),
                    emergency_contact_name=partner_data.get('emergency_contact_name'),
                    emergency_contact_phone=partner_data.get('emergency_contact_phone'),
                    delivery_zones=partner_data.get('delivery_zones'),
                    joined_date=date.today(),
                    is_active=True,
                    availability_status='offline'
                )
                partner.save()
                
                # Debug: Check if business_id was saved
                logger.info(f"Saved partner business: {partner.business}, Business ID: {partner.business.business_id if partner.business else 'None'}")
                
                # Debug: Check the actual database value with raw SQL
                with connection.cursor() as cursor:
                    cursor.execute("SELECT business_id FROM Grocery_partner WHERE id = %s", [partner.id])
                    result = cursor.fetchone()
                    logger.info(f"Raw database business_id value: {result[0] if result else 'None'}")
                    
                    # If business_id is still null/0, try direct SQL update
                    if not result[0] or result[0] == 0:
                        logger.info(f"Attempting direct SQL update with business_id: {business.business_id}")
                        cursor.execute(
                            "UPDATE Grocery_partner SET business_id = %s WHERE id = %s", 
                            [business.business_id, partner.id]
                        )
                        # Verify the update
                        cursor.execute("SELECT business_id FROM Grocery_partner WHERE id = %s", [partner.id])
                        updated_result = cursor.fetchone()
                        logger.info(f"After direct SQL update - business_id: {updated_result[0] if updated_result else 'None'}")
                
                # Return success response
                response_serializer = GroceryPartnerSerializer(partner)
                return Response({
                    "message": "Partner registered successfully! Your application is under review.",
                    "partner_data": response_serializer.data,
                    "next_steps": [
                        "Your registration is under review by the admin.",
                        "You will be notified once your account is verified.",
                        "After verification, you can start accepting delivery orders."
                    ]
                }, status=status.HTTP_201_CREATED)
                
        except Registration.DoesNotExist:
            return Response({
                "error": "User not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Business.DoesNotExist:
            return Response({
                "error": "Business not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in partner registration POST: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def put(self, request, *args, **kwargs):
        """
        Update existing partner details.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            partner = GroceryPartner.objects.get(user_id=user_id, business_id=business_id)
            
            # Validate updated data
            serializer = GroceryPartnerRegistrationSerializer(
                partner, 
                data=request.data, 
                partial=True
            )
            if not serializer.is_valid():
                return Response({
                    "error": "Validation failed.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Update partner
            serializer.save()
            
            # Return updated data
            response_serializer = GroceryPartnerSerializer(partner)
            return Response({
                "message": "Partner details updated successfully.",
                "partner_data": response_serializer.data
            }, status=status.HTTP_200_OK)
            
        except GroceryPartner.DoesNotExist:
            return Response({
                "error": "Partner not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error in partner registration PUT: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AssignOrderToPartnerView(APIView):
    """
    API view for retail business users to assign orders to delivery partners.
    Stores data in GroceryDeliverDetails table.
    """
    
    def post(self, request, *args, **kwargs):
        """
        Assign an order to a delivery partner.
        Requires user_id and business_id in query parameters.
        """
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        
        if not all([user_id, business_id]):
            return Response({
                "error": "user_id and business_id are required parameters."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Verify the user is associated with the business (retail business user)
            try:
                user = Registration.objects.get(user_id=user_id)
            except Registration.DoesNotExist:
                return Response({
                    "error": f"User with ID {user_id} not found in registrations table."
                }, status=status.HTTP_404_NOT_FOUND)
            
            try:
                business = Business.objects.get(business_id=business_id)
            except Business.DoesNotExist:
                return Response({
                    "error": f"Business with ID {business_id} not found."
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Basic serializer validation
            serializer = AssignOrderToPartnerSerializer(data=request.data)
            
            if not serializer.is_valid():
                return Response({
                    "error": "Validation failed.",
                    "details": serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get validated data
            partner_user_id = serializer.validated_data['partner_user_id']
            order_id = serializer.validated_data['order_id']
            generate_otp = serializer.validated_data.get('generate_otp', True)
            
            # Detailed partner validation in view
            try:
                partner_user = Registration.objects.get(user_id=partner_user_id)
            except Registration.DoesNotExist:
                return Response({
                    "error": "Partner user not found."
                }, status=status.HTTP_404_NOT_FOUND)
            
            try:
                partner = GroceryPartner.objects.get(user_id=partner_user_id)
            except GroceryPartner.DoesNotExist:
                return Response({
                    "error": "This user is not registered as a delivery partner."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Check partner status
            if not partner.is_active:
                return Response({
                    "error": "This delivery partner is not active."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Temporarily allow unverified partners for testing
            # if not partner.is_verified:
            #     return Response({
            #         "error": "This delivery partner is not verified."
            #     }, status=status.HTTP_400_BAD_REQUEST)
            
            # Temporarily allow all availability statuses for testing
            # if partner.availability_status != 'available':
            #     return Response({
            #         "error": "This delivery partner is not currently available."
            #     }, status=status.HTTP_400_BAD_REQUEST)
            
            # Get order and validate
            try:
                order = GroceriesOrders.objects.get(order_id=order_id)
            except GroceriesOrders.DoesNotExist:
                return Response({
                    "error": "Order not found."
                }, status=status.HTTP_404_NOT_FOUND)
            
            # Check if order is already assigned
            if GroceryDeliverDetails.objects.filter(order=order, is_active=True).exists():
                return Response({
                    "error": "This order is already assigned to a delivery partner."
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Create delivery assignment with transaction
            with transaction.atomic():
                # Debug: Log the user object details
                logger.info(f"Creating delivery assignment - User ID: {user.user_id}, User object: {user}")
                
                # Try creating with user_id directly
                delivery_detail = GroceryDeliverDetails.objects.create(
                    order=order,
                    partner=partner,
                    assigned_by_user_id=user.user_id,
                    assignment_status='assigned'
                )
                
                # Generate OTP if requested
                if generate_otp:
                    delivery_detail.generate_otp()
                
                # Update partner status to busy
                partner.availability_status = 'busy'
                partner.save(update_fields=['availability_status'])
                
                # Update order status to shipped if it was pending
                if order.order_status == 'pending':
                    order.order_status = 'shipped'
                    order.save(update_fields=['order_status'])
            
            # Return the created assignment details without complex serializer
            return Response({
                "message": "Order assigned to delivery partner successfully.",
                "delivery_detail": {
                    "delivery_detail_id": delivery_detail.delivery_detail_id,
                    "order_id": delivery_detail.order.order_id,
                    "partner_id": delivery_detail.partner.id,
                    "partner_name": f"{delivery_detail.partner.user.firstName} {delivery_detail.partner.user.lastName}",
                    "assignment_status": delivery_detail.assignment_status,
                    "assigned_at": delivery_detail.assigned_at,
                    "is_active": delivery_detail.is_active
                },
                "otp": delivery_detail.delivery_otp if delivery_detail.delivery_otp else None
            }, status=status.HTTP_201_CREATED)
            
        except Registration.DoesNotExist:
            return Response({
                "error": "User not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Business.DoesNotExist:
            return Response({
                "error": "Business not found."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error assigning order to partner: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class PartnerAssignedOrdersView(APIView):
    """
    API view to get orders assigned to a specific delivery partner.
    """
    
    def get(self, request, *args, **kwargs):
        """
        Get orders assigned to a partner with optional status filtering.
        Uses user_id to identify the delivery partner.
        """
        partner_user_id = request.query_params.get('partner_user_id')
        status_filter = request.query_params.get('status')
        
        if not partner_user_id:
            return Response({
                "error": "partner_user_id is required parameter."
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Validate partner exists by user_id
            partner = GroceryPartner.objects.select_related('user').get(user_id=partner_user_id)
            
            # Build query filters using partner object
            filters = {'partner': partner, 'is_active': True}
            if status_filter:
                filters['assignment_status'] = status_filter
            
            # Get delivery assignments
            delivery_details = GroceryDeliverDetails.objects.filter(**filters).order_by('-assigned_at')
            
            if not delivery_details.exists():
                return Response({
                    "message": "No orders found for this partner.",
                    "partner_info": {
                        "partner_id": partner.id,
                        "user_id": partner.user.user_id,
                        "partner_name": f"{partner.user.firstName} {partner.user.lastName}",
                        "vehicle_number": partner.vehicle_number
                    },
                    "orders": []
                }, status=status.HTTP_200_OK)
            
            # Create simple response without complex serializer to avoid Registration errors
            orders_data = []
            for detail in delivery_details:
                # Get order items for this order
                order_items = []
                for item in detail.order.groceriesorderitems_set.all():
                    order_items.append({
                        "order_item_id": item.order_item_id,
                        "item_id": item.item.item_id,
                        "item_name": item.item.item_name,
                        "item_image": item.item.item_image,
                        "item_category": item.item.item_category,
                        "description": item.item.description,
                        "weight": item.item.weight,
                        "unit": item.item.unit,
                        "rating": item.item.rating,
                        "quantity": item.quantity,
                        "unit_price": item.unit_price,
                        "gst": item.gst,
                        "total_price": item.total_price
                    })
                
                orders_data.append({
                    "delivery_detail_id": detail.delivery_detail_id,
                    "order_id": detail.order.order_id,
                    "order_total": detail.order.total_amount,
                    "order_type": detail.order.order_type,
                    "order_status": detail.order.order_status,
                    "delivery_address": detail.order.delivery_address,
                    "assignment_status": detail.assignment_status,
                    "assigned_at": detail.assigned_at,
                    "delivered_at": detail.delivered_at,
                    "delivery_otp": detail.delivery_otp,
                    "otp_verified_at": detail.otp_verified_at,
                    "is_active": detail.is_active,
                    "created_at": detail.created_at,
                    "updated_at": detail.updated_at,
                    "order_items": order_items
                })
            
            return Response({
                "message": f"Found {delivery_details.count()} orders for partner.",
                "partner_info": {
                    "partner_id": partner.id,
                    "user_id": partner.user.user_id,
                    "partner_name": f"{partner.user.firstName} {partner.user.lastName}",
                    "vehicle_number": partner.vehicle_number,
                    "availability_status": partner.availability_status
                },
                "total_orders": delivery_details.count(),
                "orders": orders_data
            }, status=status.HTTP_200_OK)
            
        except GroceryPartner.DoesNotExist:
            return Response({
                "error": "Delivery partner not found for this user_id."
            }, status=status.HTTP_404_NOT_FOUND)
        except Registration.DoesNotExist:
            return Response({
                "error": "User registration not found for this partner."
            }, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            logger.error(f"Error fetching partner orders: {str(e)}")
            return Response({
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

