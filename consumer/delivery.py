from django.db import transaction
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from decimal import Decimal
import json
import math
from geopy.distance import geodesic

from .models import DeliveryCharges
from .serializers import DeliveryChargesSerializer
from kirazee_app.models import Registration, UserAddress, Business


@api_view(['POST'])
def calculate_delivery_charges(request):
    """
    Calculate delivery charges based on business rules and distance
    """
    try:
        data = request.data
        business_id = data.get('business_id')
        user_address_id = data.get('user_address_id')
        cart_value = Decimal(str(data.get('cart_value', 0)))
        order_type = data.get('order_type', 'delivery')
        
        # Validate required fields
        if not all([business_id, user_address_id]):
            return Response({
                'success': False,
                'error': 'business_id and user_address_id are required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Return zero for non-delivery orders
        if order_type != 'delivery':
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': 0.00,
                    'free_delivery_applied': False,
                    'distance_km': 0,
                    'message': f'No delivery charges for {order_type} orders'
                }
            }, status=status.HTTP_200_OK)
        
        # Get business and address
        business = get_object_or_404(Business, business_id=business_id)
        user_address = get_object_or_404(UserAddress, id=user_address_id)
        
        # Calculate distance if coordinates available
        distance_km = 0
        if all([business.latitude, business.longitude, user_address.latitude, user_address.longitude]):
            business_coords = (float(business.latitude), float(business.longitude))
            user_coords = (float(user_address.latitude), float(user_address.longitude))
            distance_km = geodesic(business_coords, user_coords).kilometers
        
        # Get delivery charge configuration
        delivery_config = DeliveryCharges.objects.filter(
            business_id=business,
            is_active=True
        ).first()
        
        if not delivery_config:
            # Default delivery charges if no configuration found
            base_charge = Decimal('30.00')
            free_delivery_threshold = Decimal('500.00')
            
            if cart_value >= free_delivery_threshold:
                delivery_charges = Decimal('0.00')
                free_delivery_applied = True
            else:
                delivery_charges = base_charge
                free_delivery_applied = False
            
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': float(delivery_charges),
                    'free_delivery_applied': free_delivery_applied,
                    'distance_km': round(distance_km, 2),
                    'base_charge': float(base_charge),
                    'free_delivery_threshold': float(free_delivery_threshold),
                    'message': 'Default delivery charges applied (no business configuration found)'
                }
            }, status=status.HTTP_200_OK)
        
        # Check for free delivery threshold
        if delivery_config.free_delivery_above and cart_value >= delivery_config.free_delivery_above:
            return Response({
                'success': True,
                'data': {
                    'delivery_charges': 0.00,
                    'free_delivery_applied': True,
                    'distance_km': round(distance_km, 2),
                    'free_delivery_threshold': float(delivery_config.free_delivery_above),
                    'message': f'Free delivery applied for orders above ₹{delivery_config.free_delivery_above}'
                }
            }, status=status.HTTP_200_OK)
        
        # Calculate charges based on distance slabs
        delivery_charges = delivery_config.base_charge
        
        # Apply distance-based charges if slabs are configured
        if delivery_config.distance_slabs:
            for slab in delivery_config.distance_slabs:
                min_km = slab.get('min_km', 0)
                max_km = slab.get('max_km', float('inf'))
                charge = Decimal(str(slab.get('charge', 0)))
                
                if min_km <= distance_km < max_km:
                    delivery_charges = charge
                    break
        
        # Apply peak hour multiplier if configured
        current_hour = timezone.now().hour
        if (delivery_config.peak_hours_start and delivery_config.peak_hours_end and 
            delivery_config.peak_hour_multiplier):
            
            peak_start = delivery_config.peak_hours_start.hour
            peak_end = delivery_config.peak_hours_end.hour
            
            # Handle peak hours that span midnight
            if peak_start <= peak_end:
                is_peak_hour = peak_start <= current_hour < peak_end
            else:
                is_peak_hour = current_hour >= peak_start or current_hour < peak_end
            
            if is_peak_hour:
                delivery_charges = delivery_charges * delivery_config.peak_hour_multiplier
        
        # Apply maximum charge limit if configured
        if delivery_config.max_charge and delivery_charges > delivery_config.max_charge:
            delivery_charges = delivery_config.max_charge
        
        return Response({
            'success': True,
            'data': {
                'delivery_charges': float(delivery_charges),
                'free_delivery_applied': False,
                'distance_km': round(distance_km, 2),
                'base_charge': float(delivery_config.base_charge),
                'free_delivery_threshold': float(delivery_config.free_delivery_above) if delivery_config.free_delivery_above else None,
                'peak_hour_applied': current_hour >= (delivery_config.peak_hours_start.hour if delivery_config.peak_hours_start else 24),
                'configuration_id': delivery_config.delivery_id
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_delivery_zones(request, business_id):
    """
    Get delivery zones and charges for a business
    """
    try:
        business = get_object_or_404(Business, business_id=business_id)
        
        delivery_config = DeliveryCharges.objects.filter(
            business_id=business,
            is_active=True
        ).first()
        
        if not delivery_config:
            return Response({
                'success': False,
                'error': 'No delivery configuration found for this business'
            }, status=status.HTTP_404_NOT_FOUND)
        
        # Format distance slabs for response
        delivery_zones = []
        if delivery_config.distance_slabs:
            for i, slab in enumerate(delivery_config.distance_slabs):
                zone_name = f"Zone {i + 1}"
                min_km = slab.get('min_km', 0)
                max_km = slab.get('max_km')
                charge = slab.get('charge', 0)
                
                zone_description = f"{min_km}km"
                if max_km and max_km != float('inf'):
                    zone_description += f" - {max_km}km"
                else:
                    zone_description += "+"
                
                delivery_zones.append({
                    'zone_name': zone_name,
                    'distance_range': zone_description,
                    'min_km': min_km,
                    'max_km': max_km if max_km != float('inf') else None,
                    'charge': float(charge)
                })
        
        return Response({
            'success': True,
            'data': {
                'business_id': business_id,
                'business_name': business.businessName,
                'base_charge': float(delivery_config.base_charge),
                'max_charge': float(delivery_config.max_charge) if delivery_config.max_charge else None,
                'free_delivery_above': float(delivery_config.free_delivery_above) if delivery_config.free_delivery_above else None,
                'delivery_zones': delivery_zones,
                'peak_hours': {
                    'start': delivery_config.peak_hours_start.strftime('%H:%M') if delivery_config.peak_hours_start else None,
                    'end': delivery_config.peak_hours_end.strftime('%H:%M') if delivery_config.peak_hours_end else None,
                    'multiplier': float(delivery_config.peak_hour_multiplier) if delivery_config.peak_hour_multiplier else None
                },
                'is_active': delivery_config.is_active
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['POST'])
def create_delivery_configuration(request):
    """
    Create or update delivery charge configuration for a business
    """
    try:
        data = request.data
        business_id = data.get('business_id')
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        business = get_object_or_404(Business, business_id=business_id)
        
        # Check if configuration already exists
        existing_config = DeliveryCharges.objects.filter(business_id=business).first()
        
        if existing_config:
            # Update existing configuration
            serializer = DeliveryChargesSerializer(existing_config, data=data, partial=True)
        else:
            # Create new configuration
            serializer = DeliveryChargesSerializer(data=data)
        
        if serializer.is_valid():
            delivery_config = serializer.save(business_id=business)
            
            return Response({
                'success': True,
                'message': 'Delivery configuration saved successfully',
                'data': DeliveryChargesSerializer(delivery_config).data
            }, status=status.HTTP_201_CREATED if not existing_config else status.HTTP_200_OK)
        
        return Response({
            'success': False,
            'error': serializer.errors
        }, status=status.HTTP_400_BAD_REQUEST)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def check_delivery_availability(request):
    """
    Check if delivery is available for a specific address
    """
    try:
        business_id = request.query_params.get('business_id')
        user_address_id = request.query_params.get('user_address_id')
        latitude = request.query_params.get('latitude')
        longitude = request.query_params.get('longitude')
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        business = get_object_or_404(Business, business_id=business_id)
        
        # Get delivery configuration
        delivery_config = DeliveryCharges.objects.filter(
            business_id=business,
            is_active=True
        ).first()
        
        if not delivery_config:
            return Response({
                'success': True,
                'data': {
                    'delivery_available': True,
                    'message': 'Delivery available with default charges',
                    'max_distance_km': None
                }
            }, status=status.HTTP_200_OK)
        
        # Calculate distance if coordinates provided
        distance_km = None
        delivery_available = True
        
        if user_address_id:
            user_address = get_object_or_404(UserAddress, id=user_address_id)
            if (business.latitude and business.longitude and 
                user_address.latitude and user_address.longitude):
                business_coords = (float(business.latitude), float(business.longitude))
                user_coords = (float(user_address.latitude), float(user_address.longitude))
                distance_km = geodesic(business_coords, user_coords).kilometers
        
        elif latitude and longitude:
            if business.latitude and business.longitude:
                business_coords = (float(business.latitude), float(business.longitude))
                user_coords = (float(latitude), float(longitude))
                distance_km = geodesic(business_coords, user_coords).kilometers
        
        # Check if distance exceeds maximum delivery range
        if distance_km and delivery_config.max_delivery_distance:
            if distance_km > delivery_config.max_delivery_distance:
                delivery_available = False
        
        return Response({
            'success': True,
            'data': {
                'delivery_available': delivery_available,
                'distance_km': round(distance_km, 2) if distance_km else None,
                'max_delivery_distance': float(delivery_config.max_delivery_distance) if delivery_config.max_delivery_distance else None,
                'message': 'Delivery available' if delivery_available else 'Outside delivery area'
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(['GET'])
def get_delivery_time_estimate(request):
    """
    Get estimated delivery time for an order
    """
    try:
        business_id = request.query_params.get('business_id')
        user_address_id = request.query_params.get('user_address_id')
        order_type = request.query_params.get('order_type', 'delivery')
        
        if not business_id:
            return Response({
                'success': False,
                'error': 'business_id is required'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        business = get_object_or_404(Business, business_id=business_id)
        
        # Base preparation time based on business type
        if business.businessType == 'R02':  # Restaurant
            base_prep_time = 30  # 30 minutes
        elif business.businessType == 'R01':  # Grocery
            base_prep_time = 15  # 15 minutes
        else:
            base_prep_time = 20  # Default
        
        # Calculate delivery time if it's a delivery order
        delivery_time = 0
        if order_type == 'delivery' and user_address_id:
            user_address = get_object_or_404(UserAddress, id=user_address_id)
            
            # Calculate distance and estimate travel time
            if (business.latitude and business.longitude and 
                user_address.latitude and user_address.longitude):
                business_coords = (float(business.latitude), float(business.longitude))
                user_coords = (float(user_address.latitude), float(user_address.longitude))
                distance_km = geodesic(business_coords, user_coords).kilometers
                
                # Estimate travel time (assuming 20 km/h average speed in city)
                travel_time_minutes = (distance_km / 20) * 60
                delivery_time = max(10, int(travel_time_minutes))  # Minimum 10 minutes
        
        total_time = base_prep_time + delivery_time
        
        # Calculate estimated delivery time
        estimated_time = timezone.now() + timezone.timedelta(minutes=total_time)
        
        return Response({
            'success': True,
            'data': {
                'preparation_time_minutes': base_prep_time,
                'delivery_time_minutes': delivery_time,
                'total_time_minutes': total_time,
                'estimated_delivery_time': estimated_time.isoformat(),
                'estimated_delivery_time_formatted': estimated_time.strftime('%I:%M %p, %d %b %Y')
            }
        }, status=status.HTTP_200_OK)
        
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
