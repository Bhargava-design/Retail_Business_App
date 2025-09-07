from django.db import transaction, models
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from decimal import Decimal
import uuid
import json

from .models import Orders, OrderItems, WalletPoints, Coupons, CouponRedemptions, DeliveryCharges
from .serializers import OrderSerializer, OrderItemSerializer, OrderDetailSerializer, OrderListSerializer
from kirazee_app.models import Registration, UserAddress, Business
from business.models import MenuItems, productItems


@api_view(['POST'])
def create_order(request):
    """
    Create new order with address snapshots, delivery charges, coupon and wallet points
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        business_id = data.get('business_id')
        order_type = data.get('order_type')
        delivery_address_id = data.get('delivery_address_id')
        items = data.get('items', [])
        coupon_code = data.get('coupon_code')
        wallet_points_to_use = Decimal(str(data.get('wallet_points_to_use', 0)))
        estimated_delivery_time = data.get('estimated_delivery_time')

        # Validate required fields
        if not all([user_id, business_id, order_type, items]):
            return Response({
                'success': False,
                'error': 'Missing required fields: user_id, business_id, order_type, items'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user exists
        user = get_object_or_404(Registration, user_id=user_id)
        business = get_object_or_404(Business, business_id=business_id)

        # Calculate items total
        items_total = Decimal('0.00')
        order_items_data = []

        for item in items:
            if 'menu_item_id' in item:
                menu_item = get_object_or_404(MenuItems, item_id=item['menu_item_id'])
                item_price = menu_item.selling_price
                item_name = menu_item.item_name
                item_details = {
                    'description': menu_item.description,
                    'category': menu_item.item_category,
                    'type': menu_item.item_type,
                    'gst_percentage': float(menu_item.gst) if menu_item.gst else 0,
                    'charges': float(menu_item.charges) if menu_item.charges else 0,
                    'original_cost': float(menu_item.original_cost) if menu_item.original_cost else 0,
                    'selling_price': float(menu_item.selling_price)
                }
                order_items_data.append({
                    'menu_item_id': menu_item.item_id,
                    'product_item_id': None,
                    'item_name': item_name,
                    'quantity': item['quantity'],
                    'unit_price': item_price,
                    'total_price': item_price * item['quantity'],
                    'item_details': item_details,
                    'customizations': item.get('customizations', [])
                })
            elif 'product_item_id' in item:
                product_item = get_object_or_404(productItems, item_id=item['product_item_id'])
                item_price = product_item.selling_price
                item_name = product_item.item_name
                item_details = {
                    'description': product_item.description,
                    'category': product_item.item_category,
                    'type': product_item.item_type,
                    'gst_percentage': float(product_item.gst) if product_item.gst else 0,
                    'charges': float(product_item.charges) if product_item.charges else 0,
                    'original_cost': float(product_item.original_cost) if product_item.original_cost else 0,
                    'selling_price': float(product_item.selling_price)
                }
                order_items_data.append({
                    'menu_item_id': None,
                    'product_item_id': product_item.item_id,
                    'item_name': item_name,
                    'quantity': item['quantity'],
                    'unit_price': item_price,
                    'total_price': item_price * item['quantity'],
                    'item_details': item_details
                })

            items_total += item_price * item['quantity']

        # Calculate delivery charges
        delivery_charges = Decimal('0.00')
        if order_type == 'delivery' and delivery_address_id:
            # Get delivery address for distance calculation
            delivery_address = get_object_or_404(UserAddress, id=delivery_address_id, user=user)
            
            # Calculate delivery charges based on business rules
            try:
                delivery_config = DeliveryCharges.objects.filter(
                    business_id=business,
                    is_active=True
                ).first()
                
                if delivery_config:
                    # Simple distance-based calculation (you can enhance this)
                    delivery_charges = delivery_config.base_charge
                    
                    # Check for free delivery threshold
                    if delivery_config.free_delivery_above and items_total >= delivery_config.free_delivery_above:
                        delivery_charges = Decimal('0.00')
            except DeliveryCharges.DoesNotExist:
                delivery_charges = Decimal('30.00')  # Default delivery charge

        # Apply coupon if provided
        discount_amount = Decimal('0.00')
        coupon_applied = None
        
        if coupon_code:
            try:
                coupon = Coupons.objects.get(coupon_code=coupon_code, is_active=True)
                
                # Validate coupon
                is_valid, message = coupon.is_valid_for_user(user_id)
                if not is_valid:
                    return Response({
                        'success': False,
                        'error': f'Coupon validation failed: {message}'
                    }, status=status.HTTP_400_BAD_REQUEST)
                
                # Calculate discount
                if coupon.discount_type == 'percentage':
                    discount_amount = (items_total * coupon.discount_value) / 100
                elif coupon.discount_type == 'fixed_amount':
                    discount_amount = coupon.discount_value
                elif coupon.discount_type == 'free_delivery':
                    discount_amount = delivery_charges
                    delivery_charges = Decimal('0.00')
                
                coupon_applied = coupon
                
            except Coupons.DoesNotExist:
                return Response({
                    'success': False,
                    'error': 'Invalid coupon code'
                }, status=status.HTTP_400_BAD_REQUEST)

        # Calculate final amount
        subtotal = items_total + delivery_charges
        after_discount = subtotal - discount_amount
        
        # Apply wallet points
        wallet_points_value = Decimal('0.00')
        if wallet_points_to_use > 0:
            # Check user's wallet balance
            current_balance = WalletPoints.get_user_balance(user_id)
            if current_balance < wallet_points_to_use:
                return Response({
                    'success': False,
                    'error': f'Insufficient wallet balance. Available: {current_balance}, Requested: {wallet_points_to_use}'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            # Convert points to rupee value (10 points = 1 rupee)
            wallet_points_value = wallet_points_to_use * Decimal('0.10')

        final_amount = after_discount - wallet_points_value

        with transaction.atomic():
            # Create order
            order = Orders.objects.create(
                user_id=user,
                business_id=business,
                order_type=order_type,
                total_amount=items_total,
                discount_amount=discount_amount,
                delivery_charges=delivery_charges,
                final_amount=final_amount,
                delivery_address_id=delivery_address_id,
                coupon_code=coupon_code,
                wallet_points_used=wallet_points_to_use,
                estimated_delivery_time=estimated_delivery_time
            )

            # Create address snapshot if delivery
            if order_type == 'delivery' and delivery_address_id:
                delivery_address = UserAddress.objects.get(id=delivery_address_id)
                order.delivery_address_snapshot = order._create_address_snapshot(delivery_address)
                order.save()

            # Create order items
            created_items = []
            for item_data in order_items_data:
                order_item = OrderItems.objects.create(
                    order_id=order,
                    menu_item_id=item_data['menu_item_id'],
                    product_item_id=item_data['product_item_id'],
                    item_name_snapshot=item_data['item_name'],
                    quantity=item_data['quantity'],
                    unit_price_snapshot=item_data['unit_price'],
                    total_price=item_data['total_price'],
                    item_details_snapshot=item_data['item_details']
                )
                created_items.append(order_item)

            # Process wallet points transaction
            if wallet_points_to_use > 0:
                WalletPoints.atomic_transaction(
                    user_id=user,
                    points=wallet_points_to_use,
                    transaction_type=WalletPoints.TransactionType.SPENT,
                    description=f'Points spent on order #{order.order_number}',
                    related_order=order
                )

            # Create coupon redemption record
            if coupon_applied:
                CouponRedemptions.objects.create(
                    coupon_id=coupon_applied,
                    order_id=order,
                    user_id=user,
                    discount_amount_applied=discount_amount,
                    original_order_amount=items_total,
                    final_order_amount=after_discount
                )
                
                # Update coupon usage count
                coupon_applied.current_usage_count += 1
                coupon_applied.save()

        # Prepare response
        response_data = {
            'success': True,
            'message': 'Order created successfully',
            'data': {
                'order_id': order.order_id,
                'order_number': str(order.order_number),
                'status': order.status,
                'order_summary': {
                    'items_total': float(items_total),
                    'delivery_charges': float(delivery_charges),
                    'subtotal': float(subtotal),
                    'coupon_discount': float(discount_amount),
                    'after_coupon': float(after_discount),
                    'wallet_points_used': float(wallet_points_to_use),
                    'wallet_points_value': float(wallet_points_value),
                    'final_amount': float(final_amount)
                },
                'created_at': order.created_at.isoformat(),
                'estimated_delivery_time': order.estimated_delivery_time.isoformat() if order.estimated_delivery_time else None
            }
        }

        return Response(response_data, status=status.HTTP_201_CREATED)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_order_status(request, order_id):
    """
    Update order status using FSM transitions
    """
    try:
        order = get_object_or_404(Orders, order_id=order_id)
        action = request.data.get('action')
        business_id = request.data.get('business_id')
        notes = request.data.get('notes', '')

        # Validate business ownership
        if business_id and order.business_id.business_id != business_id:
            return Response({
                'success': False,
                'error': 'Unauthorized: Order does not belong to this business'
            }, status=status.HTTP_403_FORBIDDEN)

        # Execute FSM transition
        try:
            action = action.lower()  # Make case-insensitive
            valid_actions = {
                'confirm_order': order.confirm_order,
                'start_preparing': order.start_preparing,
                'mark_ready': order.mark_ready,
                'dispatch_for_delivery': order.dispatch_for_delivery,
                'start_travelling': order.start_travelling,
                'out_for_delivery_grocery': order.out_for_delivery_grocery,
                'complete_order': order.complete_order,
                'cancel_order': order.cancel_order
            }

            if action not in valid_actions:
                return Response({
                    'success': False,
                    'error': f'Invalid action: {action}. Valid actions are: {list(valid_actions.keys())}'
                }, status=status.HTTP_400_BAD_REQUEST)

            # Execute the transition
            valid_actions[action]()
            order.save()

            # Get available transitions
            available_transitions = []
            for transition in order.get_available_status_transitions():
                available_transitions.append({
                    'action': transition.name,
                    'target_status': transition.target,
                    'description': transition.name.replace('_', ' ').title()
                })

            return Response({
                'success': True,
                'message': 'Order status updated successfully',
                'data': {
                    'order_id': order.order_id,
                    'order_number': str(order.order_number),
                    'current_status': order.status,
                    'available_transitions': available_transitions,
                    'updated_at': order.updated_at.isoformat()
                }
            }, status=status.HTTP_200_OK)

        except Exception as transition_error:
            return Response({
                'success': False,
                'error': f'Status transition failed: {str(transition_error)}'
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_order_details(request, order_id):
    """
    Get complete order details with historical data
    """
    try:
        order = get_object_or_404(Orders, order_id=order_id)
        include_items = request.query_params.get('include_items', 'true').lower() == 'true'
        include_history = request.query_params.get('include_history', 'false').lower() == 'true'

        # Serialize order details
        serializer = OrderDetailSerializer(order, context={'request': request})
        order_data = serializer.data

        # Add order items if requested
        if include_items:
            order_items = OrderItems.objects.filter(order_id=order)
            items_serializer = OrderItemSerializer(order_items, many=True)
            order_data['items'] = items_serializer.data

        # Add business contact details
        order_data['business_contact'] = {
            'business_number': order.business_id.businessNumber if hasattr(order.business_id, 'businessNumber') else None,
            'business_whatsapp': order.business_id.businessWhatsapp if hasattr(order.business_id, 'businessWhatsapp') else None,
            'contact_mobile': order.business_id.contact_mobile if hasattr(order.business_id, 'contact_mobile') else None,
            'contact_support': order.business_id.contact_support if hasattr(order.business_id, 'contact_support') else None
        }

        return Response({
            'success': True,
            'data': order_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def list_user_orders(request, user_id):
    """
    Get paginated list of user's orders with filtering
    """
    try:
        # Validate user exists
        user = get_object_or_404(Registration, user_id=user_id)

        # Get query parameters for filtering
        status_filter = request.query_params.get('status')
        business_id_filter = request.query_params.get('business_id')
        order_type_filter = request.query_params.get('order_type')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))

        # Build query
        orders = Orders.objects.filter(user_id=user).order_by('-created_at')

        # Apply filters
        if status_filter:
            orders = orders.filter(status=status_filter)
        if business_id_filter:
            orders = orders.filter(business_id__business_id=business_id_filter)
        if order_type_filter:
            orders = orders.filter(order_type=order_type_filter)
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)

        # Paginate results
        paginator = Paginator(orders, page_size)
        page_obj = paginator.get_page(page)

        # Serialize orders
        serializer = OrderListSerializer(page_obj.object_list, many=True, context={'request': request})

        return Response({
            'success': True,
            'data': {
                'count': paginator.count,
                'next': f'/consumer/orders/user/{user_id}/?page={page + 1}' if page_obj.has_next() else None,
                'previous': f'/consumer/orders/user/{user_id}/?page={page - 1}' if page_obj.has_previous() else None,
                'results': serializer.data
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_order_analytics(request):
    """
    Get order statistics and insights
    """
    try:
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')

        # Build base query
        orders = Orders.objects.all()

        if user_id:
            orders = orders.filter(user_id__user_id=user_id)
        if business_id:
            orders = orders.filter(business_id__business_id=business_id)
        if date_from:
            orders = orders.filter(created_at__date__gte=date_from)
        if date_to:
            orders = orders.filter(created_at__date__lte=date_to)

        # Calculate summary statistics
        total_orders = orders.count()
        total_spent = orders.aggregate(total=models.Sum('final_amount'))['total'] or 0
        average_order_value = total_spent / total_orders if total_orders > 0 else 0
        total_savings = orders.aggregate(total=models.Sum('discount_amount'))['total'] or 0

        # Status breakdown
        status_breakdown = {}
        for status_choice in Orders.OrderStatus.choices:
            count = orders.filter(status=status_choice[0]).count()
            status_breakdown[status_choice[1]] = count

        # Order type breakdown
        type_breakdown = {}
        order_types = ['delivery', 'pickup', 'dine_in', 'takeaway']
        for order_type in order_types:
            count = orders.filter(order_type=order_type).count()
            type_breakdown[order_type] = count

        return Response({
            'success': True,
            'data': {
                'summary': {
                    'total_orders': total_orders,
                    'total_spent': float(total_spent),
                    'average_order_value': float(average_order_value),
                    'total_savings': float(total_savings)
                },
                'order_status_breakdown': status_breakdown,
                'order_type_breakdown': type_breakdown
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
