import traceback
from django.conf import settings
from django.db import transaction, models, connection
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404
from decimal import Decimal
import json
from datetime import datetime, timedelta

from .models import WalletPoints, Coupons, CouponRules, CouponPurchases, CouponRedemptions, PointsConfiguration
from .serializers import WalletPointsSerializer, CouponSerializer, CouponPurchaseSerializer
from kirazee_app.models import Registration, Business


def get_wallet_balance_raw_sql(user_id):
    """
    Get wallet balance using raw SQL to avoid decimal/float conflicts
    """
    with connection.cursor() as cursor:
        # Get current balance from latest transaction
        cursor.execute("""
            SELECT CAST(balance_after AS DECIMAL(10,2)) as current_balance
            FROM wallet_points 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT 1
        """, [user_id])
        
        result = cursor.fetchone()
        return Decimal(str(result[0])) if result else Decimal('0.00')

def get_expiring_points_raw_sql(user_id):
    """
    Get expiring points using raw SQL
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT COALESCE(SUM(CAST(points AS DECIMAL(10,2))), 0) as expiring_total
            FROM wallet_points 
            WHERE user_id = %s 
            AND transaction_type = 'EARNED'
            AND is_expired = 0
            AND expires_at <= DATE_ADD(NOW(), INTERVAL 30 DAY)
            AND expires_at > NOW()
        """, [user_id])
        
        result = cursor.fetchone()
        return Decimal(str(result[0])) if result else Decimal('0.00')

def get_recent_transactions_raw_sql(user_id, limit=10):
    """
    Get recent transactions using raw SQL
    """
    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT 
                wallet_id,
                transaction_type,
                CAST(points AS DECIMAL(10,2)) as points,
                CAST(balance_after AS DECIMAL(10,2)) as balance_after,
                description,
                created_at,
                is_expired
            FROM wallet_points 
            WHERE user_id = %s 
            ORDER BY created_at DESC 
            LIMIT %s
        """, [user_id, limit])
        
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

@api_view(['GET'])
def get_wallet_balance(request, user_id):
    """
    Get user's current wallet points balance and recent transactions using raw SQL
    """
    try:
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Get current balance using raw SQL
        current_balance = get_wallet_balance_raw_sql(user_id)
        
        # Get expiring points using raw SQL
        expiring_soon = get_expiring_points_raw_sql(user_id)
        
        # Get recent transactions using raw SQL
        recent_transactions = get_recent_transactions_raw_sql(user_id, 10)
        
        # Calculate rupee value safely
        balance_in_rupees = current_balance * Decimal('0.10')
        
        return Response({
            'success': True,
            'data': {
                'user_id': user_id,
                'current_balance': str(current_balance),
                'expiring_soon': str(expiring_soon),
                'recent_transactions': recent_transactions,
                'balance_in_rupees': str(balance_in_rupees)
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_wallet_transactions(request, user_id):
    """
    Get paginated wallet transaction history with filtering using raw SQL
    Query Parameters:
    - transaction_type: Filter by transaction type (EARNED, SPENT, REFUNDED, etc.)
    - date_from: Filter transactions from this date (YYYY-MM-DD)
    - date_to: Filter transactions until this date (YYYY-MM-DD)
    - page: Page number (default: 1)
    - page_size: Number of transactions per page (default: 20)
    """
    try:
        # Get query parameters with defaults
        transaction_type = request.query_params.get('transaction_type')
        date_from = request.query_params.get('date_from')
        date_to = request.query_params.get('date_to')
        page = max(1, int(request.query_params.get('page', 1)))
        page_size = max(1, min(100, int(request.query_params.get('page_size', 20))))
        offset = (page - 1) * page_size

        # Update the SQL query to match your table structure
        sql = """
        WITH filtered_transactions AS (
            SELECT 
                wp.wallet_id,
                wp.points,
                wp.transaction_type,
                wp.description,
                wp.balance_after,
                wp.created_at,
                wp.related_order_id,
                wp.related_coupon_purchase_id,
                wp.expires_at,
                wp.is_expired,
                COUNT(*) OVER() AS total_count
            FROM 
                wallet_points wp
            WHERE 
                wp.user_id = %s  # Changed from user_id_id to user_id
                {transaction_type_filter}
                {date_from_filter}
                {date_to_filter}
            ORDER BY 
                wp.created_at DESC
            LIMIT %s OFFSET %s
        )
        SELECT 
            wallet_id,
            points,
            transaction_type,
            description,
            balance_after,
            created_at,
            related_order_id,
            related_coupon_purchase_id,
            expires_at,
            is_expired,
            total_count
        FROM 
            filtered_transactions
        """
        
        # Build filter conditions
        filters = {
            'transaction_type_filter': "AND wp.transaction_type = %s" if transaction_type else "",
            'date_from_filter': "AND DATE(wp.created_at) >= %s" if date_from else "",
            'date_to_filter': "AND DATE(wp.created_at) <= %s" if date_to else ""
        }
        
        # Prepare parameters
        params = [user_id]
        
        if transaction_type:
            params.append(transaction_type)
        if date_from:
            params.append(date_from)
        if date_to:
            params.append(date_to)
            
        # Add pagination parameters
        params.extend([page_size, offset])
        
        # Format SQL with filters
        sql = sql.format(**filters)
        
        # Execute query
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            rows = cursor.fetchall()
        
        # Process results
        transactions = []
        total_count = 0
        
        if rows:
            # Convert rows to dictionaries
            transactions = [dict(zip(columns, row)) for row in rows]
            # Get total count from first row (since we used window function)
            total_count = transactions[0].pop('total_count', 0)
            
            # Format response data
            for txn in transactions:
                txn['created_at'] = txn['created_at'].isoformat() if txn['created_at'] else None
                txn['points'] = float(txn['points'])
                txn['balance_after'] = float(txn['balance_after']) if txn['balance_after'] is not None else 0.0
        
        # Calculate pagination
        total_pages = (total_count + page_size - 1) // page_size if total_count else 1
        
        # Build response
        response_data = {
            'success': True,
            'data': {
                'count': total_count,
                'page': page,
                'page_size': page_size,
                'total_pages': total_pages,
                'next': f'/consumer/wallet/{user_id}/transactions/?page={page + 1}' if page < total_pages else None,
                'previous': f'/consumer/wallet/{user_id}/transactions/?page={page - 1}' if page > 1 else None,
                'results': transactions
            }
        }
        
        return Response(response_data, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if settings.DEBUG else None
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def spend_wallet_points(request):
    """
    Spend wallet points (used internally by order system)
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        points_to_spend = Decimal(str(data.get('points', 0)))
        description = data.get('description', 'Points spent')
        order_id = data.get('order_id')
        
        if not user_id or points_to_spend <= 0:
            return Response({
                'success': False,
                'error': 'Invalid user_id or points amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Check balance
        current_balance = WalletPoints.get_user_balance(user_id)
        if current_balance < points_to_spend:
            return Response({
                'success': False,
                'error': f'Insufficient balance. Available: {current_balance}, Requested: {points_to_spend}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Process transaction
        transaction = WalletPoints.atomic_transaction(
            user_id=user,
            points=points_to_spend,
            transaction_type=WalletPoints.TransactionType.SPENT,
            description=description,
            related_order_id=order_id
        )
        
        return Response({
            'success': True,
            'message': 'Points spent successfully',
            'data': {
                'transaction_id': transaction.wallet_id,
                'points_spent': float(points_to_spend),
                'remaining_balance': float(transaction.balance_after),
                'rupee_value': float(points_to_spend * Decimal('0.10'))
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def list_available_coupons(request):
    """
    Get list of all available coupons with user-specific validation
    Query Params (all optional):
    - user_id: If provided, includes user-specific validation
    - business_id: Filter by specific business
    - cart_value: For validating minimum order requirements
    - debug: Set to true to include SQL and debug info
    """
    try:
        user_id = request.query_params.get('user_id')
        business_id = request.query_params.get('business_id')
        cart_value = Decimal(request.query_params.get('cart_value', 0))
        debug_mode = request.query_params.get('debug', '').lower() == 'true'
        
        # Debug info
        debug_info = {}
        if debug_mode:
            debug_info['query_params'] = dict(request.query_params)
        
        # Base query for active coupons with raw SQL
        current_time = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
        sql = """
        SELECT 
            c.coupon_id, c.coupon_code, c.discount_type, c.discount_value,
            c.created_by, c.business_id, c.valid_from, c.valid_to, c.is_active,
            c.max_usage_total, c.max_usage_per_user, c.current_usage_count,
            c.points_required, c.created_at, c.updated_at,
            b.business_id as business_identifier,
            b.businessName,
            cr.rule_id,
            cr.rule_type,
            cr.rule_value,
            cr.is_active as rule_active
        FROM 
            coupons c
        LEFT JOIN 
            businesses b ON c.business_id = b.business_id
        LEFT JOIN
            coupon_rules cr ON c.coupon_id = cr.coupon_id
        WHERE 
            c.is_active = TRUE
            AND c.valid_from <= %s
            AND c.valid_to >= %s
        """
        
        params = [current_time, current_time]
        
        # Add business filter if specified
        if business_id:
            sql += " AND (b.business_id = %s OR c.business_id IS NULL)"
            params.append(business_id)
        
        # Add ordering
        sql += " ORDER BY c.points_required ASC, c.valid_to ASC"
        
        if debug_mode:
            debug_info['sql_query'] = sql
            debug_info['sql_params'] = params
        
        # Execute raw SQL
        with connection.cursor() as cursor:
            cursor.execute(sql, params)
            columns = [col[0] for col in cursor.description]
            raw_coupons = [dict(zip(columns, row)) for row in cursor.fetchall()]
        
        if debug_mode:
            debug_info['raw_coupons_count'] = len(raw_coupons)
            debug_info['raw_coupons_sample'] = raw_coupons[:1] if raw_coupons else []
        
        # Group coupons and their rules
        coupons_dict = {}
        for row in raw_coupons:
            coupon_id = row['coupon_id']
            if coupon_id not in coupons_dict:
                coupons_dict[coupon_id] = {
                    'coupon_id': coupon_id,
                    'coupon_code': row['coupon_code'],
                    'discount_type': row['discount_type'],
                    'discount_value': float(row['discount_value']),
                    'description': f"{row['discount_value']}{'%' if row['discount_type'] == 'percentage' else ' OFF'}",
                    'valid_from': row['valid_from'].isoformat(),
                    'valid_to': row['valid_to'].isoformat(),
                    'points_required': row['points_required'],
                    'max_usage': row['max_usage_total'],
                    'max_usage_per_user': row['max_usage_per_user'],
                    'business_specific': bool(row['business_id']),
                    'business_id': row['business_identifier'],
                    'businessName': row['businessName'],
                    'rules': []
                }
            
            # Add rule if exists
            if row['rule_id']:
                coupons_dict[coupon_id]['rules'].append({
                    'rule_id': row['rule_id'],
                    'rule_type': row['rule_type'],
                    'rule_value': row['rule_value'],
                    'is_active': row['rule_active']
                })
        
        coupons = list(coupons_dict.values())
        
        # Get user's wallet balance if user_id provided
        user_wallet_balance = 0
        if user_id:
            try:
                user_wallet_balance = WalletPoints.get_user_balance(user_id)
            except Exception as e:
                if debug_mode:
                    debug_info['wallet_balance_error'] = str(e)
        
        # Process each coupon for eligibility
        response_data = []
        for coupon in coupons:
            # Default values
            is_valid = True
            validation_messages = []
            
            # Check coupon rules
            for rule in coupon.get('rules', []):
                if not rule['is_active']:
                    continue
                    
                if rule['rule_type'] == 'MIN_CART_VALUE' and cart_value > 0:
                    min_value = Decimal(rule['rule_value'])
                    if cart_value < min_value:
                        is_valid = False
                        validation_messages.append(f"Minimum order value of ₹{min_value} required")
            
            # User-specific validations
            if user_id:
                # Check if user has enough points
                if coupon['points_required'] > user_wallet_balance:
                    is_valid = False
                    validation_messages.append(f"Insufficient points. Required: {coupon['points_required']}")
                
                # Check max usage per user (you'll need to implement this check)
                # Example: Check if user has already used this coupon max_usage_per_user times
                
            # Add to response with validation info
            response_coupon = {
                **coupon,
                'is_eligible': is_valid,
                'can_purchase': is_valid and (not user_id or coupon['points_required'] <= user_wallet_balance),
                'validation_messages': validation_messages if not is_valid else None
            }
            
            # Remove rules from main response (unless in debug mode)
            if not debug_mode:
                response_coupon.pop('rules', None)
            
            response_data.append(response_coupon)
        
        # Prepare response
        response = {
            'success': True,
            'data': {
                'user_wallet_balance': float(user_wallet_balance) if user_id else None,
                'available_coupons': response_data,
                'total_available': len(response_data)
            }
        }
        
        # Add debug info if requested
        if debug_mode:
            response['debug'] = debug_info
        
        return Response(response, status=status.HTTP_200_OK)
        
    except Exception as e:
        error_response = {
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc() if debug_mode else None
        }
        return Response(error_response, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@api_view(['POST'])
def validate_coupon(request):
    """
    Validate coupon code for specific order context
    """
    try:
        data = request.data
        coupon_code = data.get('coupon_code')
        user_id = data.get('user_id')
        business_id = data.get('business_id')
        cart_value = Decimal(str(data.get('cart_value', 0)))
        order_type = data.get('order_type', 'delivery')
        
        if not all([coupon_code, user_id]):
            return Response({
                'success': False,
                'error': 'coupon_code and user_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        try:
            coupon = Coupons.objects.get(coupon_code=coupon_code, is_active=True)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'error': 'Invalid coupon code'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate coupon for user
        is_valid, message = coupon.is_valid_for_user(user_id)
        if not is_valid:
            return Response({
                'success': False,
                'error': message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Evaluate coupon rules
        order_context = {
            'cart_value': float(cart_value),
            'business_id': business_id,
            'order_type': order_type,
            'user_id': user_id
        }
        
        rules_satisfied = True
        failed_rules = []
        
        for rule in coupon.couponrules_set.filter(is_active=True):
            if not rule.evaluate_rule(order_context):
                rules_satisfied = False
                failed_rules.append(rule.rule_type)
        
        if not rules_satisfied:
            return Response({
                'success': False,
                'error': f'Coupon not applicable. Failed rules: {", ".join(failed_rules)}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Calculate discount amount
        discount_amount = Decimal('0.00')
        if coupon.discount_type == 'percentage':
            discount_amount = (cart_value * Decimal(str(coupon.discount_value))) / Decimal('100')
        elif coupon.discount_type == 'fixed_amount':
            discount_amount = Decimal(str(coupon.discount_value))
        elif coupon.discount_type == 'free_delivery':
            discount_amount = Decimal('30.00')  # Default delivery charge
        
        return Response({
            'success': True,
            'message': 'Coupon is valid',
            'data': {
                'coupon_id': coupon.coupon_id,
                'coupon_code': coupon.coupon_code,
                'discount_type': coupon.discount_type,
                'discount_value': float(coupon.discount_value),
                'calculated_discount': float(discount_amount),
                'valid_until': coupon.valid_to.isoformat()
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def purchase_coupon_with_points(request):
    """
    Purchase coupon using wallet points
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        coupon_id = data.get('coupon_id')
        
        if not all([user_id, coupon_id]):
            return Response({
                'success': False,
                'error': 'user_id and coupon_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        coupon = get_object_or_404(Coupons, coupon_id=coupon_id, is_active=True)
        
        # Check if coupon requires points
        if coupon.points_required <= 0:
            return Response({
                'success': False,
                'error': 'This coupon is not available for purchase with points'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check user's wallet balance
        current_balance = WalletPoints.get_user_balance(user_id)
        if current_balance < coupon.points_required:
            return Response({
                'success': False,
                'error': f'Insufficient points. Required: {coupon.points_required}, Available: {current_balance}'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if user already purchased this coupon
        existing_purchase = CouponPurchases.objects.filter(
            user_id=user,
            coupon_id=coupon
        ).first()
        
        if existing_purchase:
            return Response({
                'success': False,
                'error': 'You have already purchased this coupon'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        with transaction.atomic():
            # Create coupon purchase record
            coupon_purchase = CouponPurchases.objects.create(
                user_id=user,
                coupon_id=coupon,
                points_spent=coupon.points_required
            )
            
            # Deduct points from wallet
            WalletPoints.atomic_transaction(
                user_id=user,
                points=coupon.points_required,
                transaction_type=WalletPoints.TransactionType.SPENT,
                description=f'Purchased coupon: {coupon.coupon_code}',
                related_coupon_purchase=coupon_purchase
            )
        
        return Response({
            'success': True,
            'message': 'Coupon purchased successfully',
            'data': {
                'purchase_id': coupon_purchase.purchase_id,
                'coupon_code': coupon.coupon_code,
                'points_spent': coupon.points_required,
                'purchased_at': coupon_purchase.purchased_at.isoformat()
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_user_purchased_coupons(request, user_id):
    """
    Get list of coupons purchased by user
    """
    try:
        user = get_object_or_404(Registration, user_id=user_id)
        
        purchased_coupons = CouponPurchases.objects.filter(
            user_id=user
        ).select_related('coupon_id').order_by('-purchased_at')
        
        coupon_data = []
        for purchase in purchased_coupons:
            coupon = purchase.coupon_id
            
            # Check if coupon is still valid and not used
            is_valid, message = coupon.is_valid_for_user(user_id)
            
            # Check if already redeemed
            is_redeemed = CouponRedemptions.objects.filter(
                coupon_id=coupon,
                user_id=user
            ).exists()
            
            coupon_data.append({
                'purchase_id': purchase.purchase_id,
                'coupon_code': coupon.coupon_code,
                'discount_type': coupon.discount_type,
                'discount_value': float(coupon.discount_value),
                'points_spent': purchase.points_spent,
                'purchased_at': purchase.purchased_at.isoformat(),
                'valid_until': coupon.valid_to.isoformat(),
                'is_valid': is_valid and not is_redeemed,
                'is_redeemed': is_redeemed,
                'status_message': 'Redeemed' if is_redeemed else ('Valid' if is_valid else message)
            })
        
        return Response({
            'success': True,
            'data': {
                'purchased_coupons': coupon_data
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def add_wallet_points(request):
    """
    Add points to user's wallet (admin/system use)
    """
    try:
        data = request.data
        user_id = data.get('user_id')
        points_to_add = Decimal(str(data.get('points', 0)))
        transaction_type = data.get('transaction_type', WalletPoints.TransactionType.EARNED)
        description = data.get('description', 'Points added')
        expires_days = int(data.get('expires_days', 365))  # Default 1 year expiry
        
        if not user_id or points_to_add <= 0:
            return Response({
                'success': False,
                'error': 'Invalid user_id or points amount'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        user = get_object_or_404(Registration, user_id=user_id)
        
        # Set expiry date for earned points
        expires_at = None
        if transaction_type == WalletPoints.TransactionType.EARNED:
            expires_at = timezone.now() + timedelta(days=expires_days)
        
        # Add points
        transaction = WalletPoints.atomic_transaction(
            user_id=user,
            points=points_to_add,
            transaction_type=transaction_type,
            description=description,
            expires_at=expires_at
        )
        
        return Response({
            'success': True,
            'message': 'Points added successfully',
            'data': {
                'transaction_id': transaction.wallet_id,
                'points_added': float(points_to_add),
                'new_balance': float(transaction.balance_after),
                'expires_at': expires_at.isoformat() if expires_at else None
            }
        }, status=status.HTTP_201_CREATED)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
