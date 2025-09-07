from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from consumer.models import Coupons, CouponRules
from consumer.serializers import CouponSerializer, CouponRulesSerializer
from kirazee_app.models import BusinessMapping
import json
from datetime import datetime
from kirazee_app.models import Business
from django.db import connection

@api_view(['POST'])
def create_coupon(request):
    """
    Create a new coupon by business owner
    POST /business/create-coupon/
    Required: user_id, business_id (for multi-business support)
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not business_id:
            return Response({
                'success': False,
                'message': 'business_id is required for coupon creation'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Verify user owns this business or its master business
        try:
            business = Business.objects.get(business_id=business_id)
            
            # If this is a sublevel business, check authorization against master
            if business.level and business.level.lower() != 'master' and business.master:
                business_mapping = BusinessMapping.objects.get(
                    user_id=user_id, 
                    business_id=business.master,
                    status=True
                )
            else:
                business_mapping = BusinessMapping.objects.get(
                    user_id=user_id, 
                    business_id=business_id,
                    status=True
                )
        except (Business.DoesNotExist, BusinessMapping.DoesNotExist):
            return Response({
                'success': False,
                'message': 'You are not authorized to create coupons for this business'
            }, status=status.HTTP_403_FORBIDDEN)

        # Prepare coupon data
        coupon_data = request.data.copy()
        coupon_data['business_id'] = business_id
        coupon_data['created_by'] = 'business_owner'

        # Validate dates
        valid_from = coupon_data.get('valid_from')
        valid_to = coupon_data.get('valid_to')
        
        if valid_from and valid_to:
            if datetime.fromisoformat(valid_from.replace('Z', '+00:00')) >= datetime.fromisoformat(valid_to.replace('Z', '+00:00')):
                return Response({
                    'success': False,
                    'message': 'valid_from must be before valid_to'
                }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            # Create coupon
            coupon_serializer = CouponSerializer(data=coupon_data)
            if coupon_serializer.is_valid():
                coupon = coupon_serializer.save()
                
                # Create coupon rules if provided
                rules_data = request.data.get('rules', [])
                created_rules = []
                
                for rule_data in rules_data:
                    rule_data['coupon_id'] = coupon.coupon_id
                    rule_serializer = CouponRulesSerializer(data=rule_data)
                    if rule_serializer.is_valid():
                        rule = rule_serializer.save()
                        created_rules.append(rule_serializer.data)
                    else:
                        return Response({
                            'success': False,
                            'message': 'Invalid rule data',
                            'errors': rule_serializer.errors
                        }, status=status.HTTP_400_BAD_REQUEST)

                return Response({
                    'success': True,
                    'message': 'Coupon created successfully',
                    'data': {
                        'coupon': coupon_serializer.data,
                        'rules': created_rules
                    }
                }, status=status.HTTP_201_CREATED)
            else:
                return Response({
                    'success': False,
                    'message': 'Invalid coupon data',
                    'errors': coupon_serializer.errors
                }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error creating coupon: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_user_businesses(request):
    """
    Get all businesses owned by a user with hierarchical structure (master/sublevel)
    GET /business/user-businesses/?user_id=123
    """
    try:
        user_id = request.query_params.get('user_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get all businesses for this user
        business_mappings = BusinessMapping.objects.filter(
            user_id=user_id,
            status=True
        ).select_related('business')

        if not business_mappings.exists():
            return Response({
                'success': False,
                'message': 'No businesses found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        businesses = []
        for mapping in business_mappings:
            business = mapping.business
            business_data = {
                'business_id': business.business_id,
                'business_name': business.businessName,
                'business_type': business.businessType,
                'business_category': business.businessCategory,
                'level': business.level,
                'master': business.master,
                'city': business.city,
                'status': business.status,
                'is_verified': business.is_verified,
                'sub_level': []  # Initialize for child businesses
            }
            
            # If this is a master business, get its sublevel businesses
            level_val = str(business.level or "").strip().lower()
            if level_val == "master":
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT business_id, businessName, businessType, businessCategory, 
                               level, master, city, status, is_verified
                        FROM businesses
                        WHERE master = %s AND status = 1
                        ORDER BY created_at ASC
                        """,
                        [business.business_id],
                    )
                    columns = [col[0] for col in cursor.description]
                    sub_rows = [dict(zip(columns, row)) for row in cursor.fetchall()]

                # Add sublevel businesses
                for sub_business in sub_rows:
                    business_data['sub_level'].append({
                        'business_id': sub_business['business_id'],
                        'business_name': sub_business['businessName'],
                        'business_type': sub_business['businessType'],
                        'business_category': sub_business['businessCategory'],
                        'level': sub_business['level'],
                        'master': sub_business['master'],
                        'city': sub_business['city'],
                        'status': sub_business['status'],
                        'is_verified': sub_business['is_verified']
                    })
            
            businesses.append(business_data)

        # Count total businesses including sublevels
        total_count = len(businesses)
        sublevel_count = sum(len(b['sub_level']) for b in businesses)
        
        return Response({
            'success': True,
            'message': f'Found {total_count} main businesses with {sublevel_count} sublevels for user',
            'data': {
                'user_id': user_id,
                'businesses': businesses,
                'main_business_count': total_count,
                'sublevel_business_count': sublevel_count,
                'total_business_count': total_count + sublevel_count
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error fetching user businesses: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def list_business_coupons(request):
    """
    Securely list all coupons from all businesses owned by a user (master + sublevel)
    POST /business/coupons/
    Body: {"user_id": 123, "filters": {...}}
    """
    try:
        # Input validation and sanitization
        user_id = request.data.get('user_id')
        filters = request.data.get('filters', {})
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user_id is numeric to prevent injection
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Invalid user_id format'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate optional filters
        status_filter = filters.get('status', 'all')
        business_type_filter = filters.get('business_type')
        date_from = filters.get('date_from')
        date_to = filters.get('date_to')
        
        # Sanitize status filter
        if status_filter not in ['all', 'active', 'inactive']:
            status_filter = 'all'

        with connection.cursor() as cursor:
            # Step 1: Get all businesses for this user with parameterized query
            cursor.execute("""
                SELECT DISTINCT b.business_id, b.businessName, b.businessType, 
                       b.level, b.master, b.city, b.status, b.is_verified
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1 AND b.status = 1
            """, [user_id])
            
            business_rows = cursor.fetchall()
            if not business_rows:
                return Response({
                    'success': False,
                    'message': 'No businesses found for this user'
                }, status=status.HTTP_404_NOT_FOUND)

            # Step 2: Collect business IDs and get sublevel businesses
            all_business_ids = []
            business_details = {}
            
            for row in business_rows:
                business_id = row[0]
                all_business_ids.append(business_id)
                business_details[business_id] = {
                    'business_id': row[0],
                    'business_name': row[1],
                    'business_type': row[2],
                    'level': row[3],
                    'master': row[4],
                    'city': row[5],
                    'status': row[6],
                    'is_verified': row[7]
                }
                
                # If master business, get sublevels
                if str(row[3] or "").strip().lower() == "master":
                    cursor.execute("""
                        SELECT business_id, businessName, businessType, level, 
                               master, city, status, is_verified
                        FROM businesses
                        WHERE master = %s AND status = 1
                    """, [business_id])
                    
                    sub_rows = cursor.fetchall()
                    for sub_row in sub_rows:
                        sub_id = sub_row[0]
                        all_business_ids.append(sub_id)
                        business_details[sub_id] = {
                            'business_id': sub_row[0],
                            'business_name': sub_row[1],
                            'business_type': sub_row[2],
                            'level': sub_row[3],
                            'master': sub_row[4],
                            'city': sub_row[5],
                            'status': sub_row[6],
                            'is_verified': sub_row[7]
                        }

            # Step 3: Build secure coupon query with filters
            coupon_query = """
                SELECT c.coupon_id, c.coupon_code, c.discount_type, c.discount_value,
                       c.business_id, c.valid_from, c.valid_to, c.is_active,
                       c.max_usage_total, c.max_usage_per_user, c.current_usage_count,
                       c.points_required, c.created_by, c.created_at, c.updated_at
                FROM coupons c
                WHERE c.business_id IN ({})
            """.format(','.join(['%s'] * len(all_business_ids)))
            
            query_params = all_business_ids.copy()
            
            # Add status filter
            if status_filter == 'active':
                coupon_query += " AND c.is_active = 1"
            elif status_filter == 'inactive':
                coupon_query += " AND c.is_active = 0"
            
            # Add business type filter
            if business_type_filter:
                # Validate business type format (R01, R02, etc.)
                if business_type_filter.upper() in ['R01', 'R02', 'R03']:
                    coupon_query += """
                        AND c.business_id IN (
                            SELECT business_id FROM businesses 
                            WHERE businessType = %s
                        )
                    """
                    query_params.append(business_type_filter.upper())
            
            # Add date filters
            if date_from:
                coupon_query += " AND c.created_at >= %s"
                query_params.append(date_from)
            if date_to:
                coupon_query += " AND c.created_at <= %s"
                query_params.append(date_to)
            
            coupon_query += " ORDER BY c.created_at DESC"
            
            # Execute secure coupon query
            cursor.execute(coupon_query, query_params)
            coupon_rows = cursor.fetchall()
            
            # Step 4: Process coupon data with usage statistics
            coupon_list = []
            grouped_coupons = {}
            
            for row in coupon_rows:
                coupon_id = row[0]
                business_id = row[4]
                
                # Get coupon rules securely
                cursor.execute("""
                    SELECT rule_id, rule_type, rule_value, is_active, created_at
                    FROM coupon_rules
                    WHERE coupon_id = %s AND is_active = 1
                """, [coupon_id])
                
                rule_rows = cursor.fetchall()
                rules = []
                for rule_row in rule_rows:
                    rules.append({
                        'rule_id': rule_row[0],
                        'rule_type': rule_row[1],
                        'rule_value': json.loads(rule_row[2]) if rule_row[2] else {},
                        'is_active': rule_row[3],
                        'created_at': rule_row[4].isoformat() if rule_row[4] else None
                    })
                
                # Get redemption statistics (handle missing table gracefully)
                total_redemptions = 0
                total_discount_given = 0.0
                
                try:
                    cursor.execute("""
                        SELECT COUNT(*) as total_redemptions,
                               COALESCE(SUM(discount_amount_applied), 0) as total_discount_given
                        FROM coupon_redemptions
                        WHERE coupon_id = %s
                    """, [coupon_id])
                    
                    stats_row = cursor.fetchone()
                    total_redemptions = stats_row[0] if stats_row else 0
                    total_discount_given = float(stats_row[1]) if stats_row else 0.0
                except Exception as e:
                    # Table doesn't exist or other error - use default values
                    if "doesn't exist" in str(e):
                        total_redemptions = 0
                        total_discount_given = 0.0
                    else:
                        raise e
                
                coupon_data = {
                    'coupon_id': row[0],
                    'coupon_code': row[1],
                    'discount_type': row[2],
                    'discount_value': float(row[3]),
                    'business_id': row[4],
                    'business_info': business_details.get(business_id, {}),
                    'valid_from': row[5].isoformat() if row[5] else None,
                    'valid_to': row[6].isoformat() if row[6] else None,
                    'is_active': bool(row[7]),
                    'max_usage_total': row[8],
                    'max_usage_per_user': row[9],
                    'current_usage_count': row[10],
                    'points_required': row[11],
                    'created_by': row[12],
                    'created_at': row[13].isoformat() if row[13] else None,
                    'updated_at': row[14].isoformat() if row[14] else None,
                    'rules': rules,
                    'usage_stats': {
                        'total_redemptions': total_redemptions,
                        'current_usage_count': row[10],
                        'max_usage_total': row[8],
                        'remaining_uses': row[8] - row[10] if row[8] else None,
                        'total_discount_given': total_discount_given
                    }
                }
                
                coupon_list.append(coupon_data)
                
                # Group by business
                if business_id not in grouped_coupons:
                    grouped_coupons[business_id] = {
                        'business_info': business_details.get(business_id, {}),
                        'coupons': []
                    }
                grouped_coupons[business_id]['coupons'].append(coupon_data)

        return Response({
            'success': True,
            'message': f'Securely retrieved {len(coupon_list)} coupons from {len(all_business_ids)} businesses',
            'data': {
                'all_coupons': coupon_list,
                'grouped_by_business': grouped_coupons,
                'total_coupon_count': len(coupon_list),
                'total_business_count': len(all_business_ids),
                'filters_applied': filters
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving coupons: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['PUT'])
def update_coupon(request, coupon_id):
    """
    Update a coupon by business owner
    PUT /business/coupons/{coupon_id}/
    """
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Business not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get coupon and verify ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id=business_id)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Coupon not found or not owned by this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Update coupon
        coupon_data = request.data.copy()
        coupon_data.pop('user_id', None)  # Remove user_id from update data
        
        coupon_serializer = CouponSerializer(coupon, data=coupon_data, partial=True)
        if coupon_serializer.is_valid():
            coupon_serializer.save()
            
            return Response({
                'success': True,
                'message': 'Coupon updated successfully',
                'data': coupon_serializer.data
            }, status=status.HTTP_200_OK)
        else:
            return Response({
                'success': False,
                'message': 'Invalid coupon data',
                'errors': coupon_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error updating coupon: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# @api_view(['PATCH'])
# def toggle_coupon_status(request, coupon_id):
#     """
#     Activate/Deactivate a coupon (soft delete toggle)
#     PATCH /business/coupons/{coupon_id}/toggle/
#     Body: {"user_id": 14774, "action": "activate" or "deactivate"}
#     """
#     try:
#         user_id = request.data.get('user_id')
#         action = request.data.get('action', '').lower()
        
#         if not user_id:
#             return Response({
#                 'success': False,
#                 'message': 'user_id is required'
#             }, status=status.HTTP_400_BAD_REQUEST)
        
#         if action not in ['activate', 'deactivate']:
#             return Response({
#                 'success': False,
#                 'message': 'action must be either "activate" or "deactivate"'
#             }, status=status.HTTP_400_BAD_REQUEST)

#         # Validate user_id format
#         try:
#             user_id = int(user_id)
#         except (ValueError, TypeError):
#             return Response({
#                 'success': False,
#                 'message': 'Invalid user_id format'
#             }, status=status.HTTP_400_BAD_REQUEST)

#         # Get all businesses owned by user (including sublevels)
#         with connection.cursor() as cursor:
#             cursor.execute("""
#                 SELECT DISTINCT b.business_id
#                 FROM business_mapping bm
#                 INNER JOIN businesses b ON bm.business_id = b.business_id
#                 WHERE bm.user_id = %s AND bm.status = 1
#                 UNION
#                 SELECT DISTINCT sb.business_id
#                 FROM business_mapping bm
#                 INNER JOIN businesses mb ON bm.business_id = mb.business_id
#                 INNER JOIN businesses sb ON mb.business_id = sb.master
#                 WHERE bm.user_id = %s AND bm.status = 1 AND sb.status = 1
#             """, [user_id, user_id])
            
#             user_business_ids = [row[0] for row in cursor.fetchall()]

#         if not user_business_ids:
#             return Response({
#                 'success': False,
#                 'message': 'No businesses found for this user'
#             }, status=status.HTTP_404_NOT_FOUND)

#         # Get coupon and verify ownership
#         try:
#             coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__in=user_business_ids)
#         except Coupons.DoesNotExist:
#             return Response({
#                 'success': False,
#                 'message': 'Coupon not found or not owned by this user'
#             }, status=status.HTTP_404_NOT_FOUND)

#         # Toggle coupon status
#         new_status = True if action == 'activate' else False
#         coupon.is_active = new_status
#         coupon.save()

#         return Response({
#             'success': True,
#             'message': f'Coupon {action}d successfully',
#             'data': {
#                 'coupon_id': coupon_id,
#                 'coupon_code': coupon.coupon_code,
#                 'is_active': coupon.is_active,
#                 'action_performed': action
#             }
#         }, status=status.HTTP_200_OK)

#     except Exception as e:
#         return Response({
#             'success': False,
#             'message': f'Error {action}ing coupon: {str(e)}'
#         }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['DELETE'])
def delete_coupon(request, coupon_id):
    """
    Permanently delete a coupon by business owner
    DELETE /business/coupons/{coupon_id}/
    Body: {"user_id": 14774, "confirm_delete": true}
    """
    try:
        user_id = request.data.get('user_id')
        confirm_delete = request.data.get('confirm_delete', False)
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if not confirm_delete:
            return Response({
                'success': False,
                'message': 'confirm_delete must be true for permanent deletion'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Validate user_id format
        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return Response({
                'success': False,
                'message': 'Invalid user_id format'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get all businesses owned by user (including sublevels)
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT b.business_id
                FROM business_mapping bm
                INNER JOIN businesses b ON bm.business_id = b.business_id
                WHERE bm.user_id = %s AND bm.status = 1
                UNION
                SELECT DISTINCT sb.business_id
                FROM business_mapping bm
                INNER JOIN businesses mb ON bm.business_id = mb.business_id
                INNER JOIN businesses sb ON mb.business_id = sb.master
                WHERE bm.user_id = %s AND bm.status = 1 AND sb.status = 1
            """, [user_id, user_id])
            
            user_business_ids = [row[0] for row in cursor.fetchall()]

        if not user_business_ids:
            return Response({
                'success': False,
                'message': 'No businesses found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Get coupon and verify ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id__in=user_business_ids)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Coupon not found or not owned by this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Check if coupon has been used (has redemptions)
        try:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM coupon_redemptions 
                    WHERE coupon_id = %s
                """, [coupon_id])
                redemption_count = cursor.fetchone()[0]
                
                if redemption_count > 0:
                    return Response({
                        'success': False,
                        'message': f'Cannot permanently delete coupon. It has {redemption_count} redemptions. Use deactivate instead.'
                    }, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            # If coupon_redemptions table doesn't exist, allow deletion
            pass

        # Store coupon info before deletion
        coupon_code = coupon.coupon_code
        business_id_str = str(coupon.business_id)

        # Permanently delete the coupon
        coupon.delete()

        return Response({
            'success': True,
            'message': 'Coupon permanently deleted successfully',
            'data': {
                'deleted_coupon_id': coupon_id,
                'deleted_coupon_code': coupon_code,
                'business_id': business_id_str
            }
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error deleting coupon: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def add_coupon_rule(request, coupon_id):
    """
    Add a rule to existing coupon
    POST /business/coupons/{coupon_id}/rules/
    """
    try:
        user_id = request.data.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Business not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        # Verify coupon ownership
        try:
            coupon = Coupons.objects.get(coupon_id=coupon_id, business_id=business_id)
        except Coupons.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Coupon not found or not owned by this business'
            }, status=status.HTTP_404_NOT_FOUND)

        # Create rule
        rule_data = request.data.copy()
        rule_data['coupon_id'] = coupon_id
        rule_data.pop('user_id', None)

        rule_serializer = CouponRulesSerializer(data=rule_data)
        if rule_serializer.is_valid():
            rule = rule_serializer.save()
            return Response({
                'success': True,
                'message': 'Coupon rule added successfully',
                'data': rule_serializer.data
            }, status=status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Invalid rule data',
                'errors': rule_serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error adding coupon rule: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def coupon_analytics(request):
    """
    Get coupon usage analytics for business
    GET /business/coupon-analytics/?user_id=123
    """
    try:
        user_id = request.GET.get('user_id')
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Get business_id from business mapping
        try:
            business_mapping = BusinessMapping.objects.get(user_id=user_id)
            business_id = business_mapping.business_id
        except BusinessMapping.DoesNotExist:
            return Response({
                'success': False,
                'message': 'Business not found for this user'
            }, status=status.HTTP_404_NOT_FOUND)

        from django.db import connection
        
        with connection.cursor() as cursor:
            # Get coupon analytics
            cursor.execute("""
                SELECT 
                    c.coupon_code,
                    c.discount_type,
                    c.discount_value,
                    c.max_usage_total,
                    c.current_usage_count,
                    COALESCE(SUM(cr.discount_amount_applied), 0) as total_discount_given,
                    COUNT(cr.redemption_id) as total_redemptions,
                    c.created_at
                FROM coupons c
                LEFT JOIN coupon_redemptions cr ON c.coupon_id = cr.coupon_id
                WHERE c.business_id = %s
                GROUP BY c.coupon_id
                ORDER BY c.created_at DESC
            """, [business_id])
            
            columns = [col[0] for col in cursor.description]
            analytics_data = [dict(zip(columns, row)) for row in cursor.fetchall()]

        return Response({
            'success': True,
            'message': 'Coupon analytics retrieved successfully',
            'data': analytics_data
        }, status=status.HTTP_200_OK)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving analytics: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
