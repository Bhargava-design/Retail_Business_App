from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction
from consumer.models import DeliveryCharges
from consumer.serializers import DeliveryChargesSerializer
from kirazee_app.models import BusinessMapping
import json

@api_view(['POST'])
def configure_delivery_charges(request):
    """
    Configure delivery charges for business
    POST /business/configure-delivery/
    Body: {
        "user_id": 14774,
        "business_id": "KIR147712008250306",  // Optional - if not provided, derived from user_id
        "base_charge": 30.00,
        "distance_slabs": [...],
        "free_delivery_above": 500.00,
        ...
    }
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # If business_id not provided, get it from business mapping
        if not business_id:
            try:
                business_mapping = BusinessMapping.objects.get(user_id=user_id)
                business_id = business_mapping.business_id
            except BusinessMapping.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found for this user'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # Verify user has access to the specified business_id (including sublevel businesses)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        -- Direct business ownership
                        SELECT b.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses b ON bm.business_id = b.business_id
                        WHERE bm.user_id = %s AND bm.status = 1 AND b.business_id = %s
                        
                        UNION
                        
                        -- Sublevel businesses owned by user's master business
                        SELECT sb.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses mb ON bm.business_id = mb.business_id
                        INNER JOIN businesses sb ON mb.business_id = sb.master
                        WHERE bm.user_id = %s AND bm.status = 1 AND sb.business_id = %s AND sb.status = 1
                    ) AS accessible_businesses
                """, [user_id, business_id, user_id, business_id])
                
                has_access = cursor.fetchone()[0] > 0
                if not has_access:
                    return Response({
                        'success': False,
                        'message': 'User does not have access to this business'
                    }, status=status.HTTP_403_FORBIDDEN)

        # Prepare delivery data
        delivery_data = request.data.copy()
        delivery_data['business_id'] = business_id

        # Check if configuration already exists
        existing_config = DeliveryCharges.objects.filter(business_id=business_id).first()
        
        if existing_config:
            # Update existing configuration
            serializer = DeliveryChargesSerializer(existing_config, data=delivery_data, partial=True)
        else:
            # Create new configuration
            serializer = DeliveryChargesSerializer(data=delivery_data)

        if serializer.is_valid():
            delivery_config = serializer.save()
            return Response({
                'success': True,
                'message': 'Delivery charges configured successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK if existing_config else status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Invalid delivery configuration data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error configuring delivery charges: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_delivery_configuration(request):
    """
    Get delivery configuration for business
    GET /business/delivery-config/?user_id=123&business_id=KIR147712008250306
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # If business_id not provided, get it from business mapping
        if not business_id:
            try:
                business_mapping = BusinessMapping.objects.get(user_id=user_id)
                business_id = business_mapping.business_id
            except BusinessMapping.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found for this user'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # Verify user has access to the specified business_id (including sublevel businesses)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        -- Direct business ownership
                        SELECT b.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses b ON bm.business_id = b.business_id
                        WHERE bm.user_id = %s AND bm.status = 1 AND b.business_id = %s
                        
                        UNION
                        
                        -- Sublevel businesses owned by user's master business
                        SELECT sb.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses mb ON bm.business_id = mb.business_id
                        INNER JOIN businesses sb ON mb.business_id = sb.master
                        WHERE bm.user_id = %s AND bm.status = 1 AND sb.business_id = %s AND sb.status = 1
                    ) AS accessible_businesses
                """, [user_id, business_id, user_id, business_id])
                
                has_access = cursor.fetchone()[0] > 0
                if not has_access:
                    return Response({
                        'success': False,
                        'message': 'User does not have access to this business'
                    }, status=status.HTTP_403_FORBIDDEN)

        # Get delivery configuration
        try:
            delivery_config = DeliveryCharges.objects.get(business_id=business_id, is_active=True)
            serializer = DeliveryChargesSerializer(delivery_config)
            
            return Response({
                'success': True,
                'message': 'Delivery configuration retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except DeliveryCharges.DoesNotExist:
            return Response({
                'success': False,
                'message': 'No delivery configuration found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving delivery configuration: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def configure_points_system(request):
    """
    Configure points earning system for business
    POST /business/configure-points/
    Body: {
        "user_id": 14774,
        "business_id": "KIR147712008250306",  // Optional - if not provided, derived from user_id
        "points_per_rupee_spent": 2.00,
        "points_per_rupee_value": 0.10,
        ...
    }
    """
    try:
        user_id = request.data.get('user_id')
        business_id = request.data.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # If business_id not provided, get it from business mapping
        if not business_id:
            try:
                business_mapping = BusinessMapping.objects.get(user_id=user_id)
                business_id = business_mapping.business_id
            except BusinessMapping.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found for this user'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # Verify user has access to the specified business_id (including sublevel businesses)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        -- Direct business ownership
                        SELECT b.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses b ON bm.business_id = b.business_id
                        WHERE bm.user_id = %s AND bm.status = 1 AND b.business_id = %s
                        
                        UNION
                        
                        -- Sublevel businesses owned by user's master business
                        SELECT sb.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses mb ON bm.business_id = mb.business_id
                        INNER JOIN businesses sb ON mb.business_id = sb.master
                        WHERE bm.user_id = %s AND bm.status = 1 AND sb.business_id = %s AND sb.status = 1
                    ) AS accessible_businesses
                """, [user_id, business_id, user_id, business_id])
                
                has_access = cursor.fetchone()[0] > 0
                if not has_access:
                    return Response({
                        'success': False,
                        'message': 'User does not have access to this business'
                    }, status=status.HTTP_403_FORBIDDEN)

        from consumer.models import PointsConfiguration
        from consumer.serializers import PointsConfigurationSerializer

        # Prepare points data
        points_data = request.data.copy()
        points_data['business_id'] = business_id

        # Check if configuration already exists
        existing_config = PointsConfiguration.objects.filter(business_id=business_id).first()
        
        if existing_config:
            # Update existing configuration
            serializer = PointsConfigurationSerializer(existing_config, data=points_data, partial=True)
        else:
            # Create new configuration
            serializer = PointsConfigurationSerializer(data=points_data)

        if serializer.is_valid():
            points_config = serializer.save()
            return Response({
                'success': True,
                'message': 'Points system configured successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK if existing_config else status.HTTP_201_CREATED)
        else:
            return Response({
                'success': False,
                'message': 'Invalid points configuration data',
                'errors': serializer.errors
            }, status=status.HTTP_400_BAD_REQUEST)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error configuring points system: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_points_configuration(request):
    """
    Get points configuration for business
    GET /business/points-config/?user_id=123&business_id=KIR147712008250306
    """
    try:
        user_id = request.GET.get('user_id')
        business_id = request.GET.get('business_id')
        
        if not user_id:
            return Response({
                'success': False,
                'message': 'user_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)

        # If business_id not provided, get it from business mapping
        if not business_id:
            try:
                business_mapping = BusinessMapping.objects.get(user_id=user_id)
                business_id = business_mapping.business_id
            except BusinessMapping.DoesNotExist:
                return Response({
                    'success': False,
                    'message': 'Business not found for this user'
                }, status=status.HTTP_404_NOT_FOUND)
        else:
            # Verify user has access to the specified business_id (including sublevel businesses)
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT COUNT(*) FROM (
                        -- Direct business ownership
                        SELECT b.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses b ON bm.business_id = b.business_id
                        WHERE bm.user_id = %s AND bm.status = 1 AND b.business_id = %s
                        
                        UNION
                        
                        -- Sublevel businesses owned by user's master business
                        SELECT sb.business_id
                        FROM business_mapping bm
                        INNER JOIN businesses mb ON bm.business_id = mb.business_id
                        INNER JOIN businesses sb ON mb.business_id = sb.master
                        WHERE bm.user_id = %s AND bm.status = 1 AND sb.business_id = %s AND sb.status = 1
                    ) AS accessible_businesses
                """, [user_id, business_id, user_id, business_id])
                
                has_access = cursor.fetchone()[0] > 0
                if not has_access:
                    return Response({
                        'success': False,
                        'message': 'User does not have access to this business'
                    }, status=status.HTTP_403_FORBIDDEN)

        from consumer.models import PointsConfiguration
        from consumer.serializers import PointsConfigurationSerializer

        # Get points configuration
        try:
            points_config = PointsConfiguration.objects.get(business_id=business_id, is_active=True)
            serializer = PointsConfigurationSerializer(points_config)
            
            return Response({
                'success': True,
                'message': 'Points configuration retrieved successfully',
                'data': serializer.data
            }, status=status.HTTP_200_OK)
            
        except PointsConfiguration.DoesNotExist:
            return Response({
                'success': False,
                'message': 'No points configuration found for this business'
            }, status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response({
            'success': False,
            'message': f'Error retrieving points configuration: {str(e)}'
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
