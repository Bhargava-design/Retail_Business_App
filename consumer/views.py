from django.db import connection
from rest_framework.decorators import api_view
from rest_framework.response import Response
from django.http import JsonResponse
import datetime, json
from rest_framework import status
from .serializers import BusinessSerializer, MenuItemsSerializer, productItemsSerializer, BusinessnearbySerializer
from business.models import Business, MenuItems, productItems
from .models import MenuCart
from geopy.distance import geodesic
from django.utils.timezone import now
import requests

#get near by businesses
@api_view(['GET'])
def nearby_businesses(request):
    # Get query parameters
    business_type = request.query_params.get('type')
    latitude = request.query_params.get('lat')
    longitude = request.query_params.get('lng')
    address = request.query_params.get('address')
    radius_km = float(request.query_params.get('radius', 1))  # Default 1km radius
    
    # If address is provided, geocode it to get coordinates
    if address:
        try:
            response = requests.get(
                'https://nominatim.openstreetmap.org/search',
                params={'q': address, 'format': 'json', 'limit': 1}
            )
            if response.status_code == 200 and response.json():
                location = response.json()[0]
                latitude = location['lat']
                longitude = location['lon']
        except Exception as e:
            return Response(
                {'error': 'Failed to geocode address'},
                status=status.HTTP_400_BAD_REQUEST
            )

    # If coordinates are available, perform distance-based query
    if latitude and longitude:
        try:
            user_location = (float(latitude), float(longitude))
            
            # Get all businesses (or filtered by type)
            businesses = Business.objects.exclude(latitude__isnull=True, longitude__isnull=True)
            if business_type:
                businesses = businesses.filter(businessType=business_type)
            
            # Calculate distance for each business and filter by radius
            nearby_businesses = []
            for business in businesses:
                if business.latitude is not None and business.longitude is not None:
                    business_location = (business.latitude, business.longitude)
                    distance = geodesic(user_location, business_location).kilometers
                    if distance <= radius_km:
                        business.distance_km = round(distance, 2)  # Round to 2 decimal places
                        nearby_businesses.append(business)
            
            # Sort by distance
            nearby_businesses.sort(key=lambda x: x.distance_km)
            
            serializer = BusinessnearbySerializer(nearby_businesses, many=True)
            return Response(serializer.data)
            
        except (ValueError, TypeError) as e:
            return Response(
                {'error': 'Invalid coordinates', 'details': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )
    else:
        # Fallback to non-location based query
        businesses = Business.objects.all()
        if business_type:
            businesses = businesses.filter(businessType=business_type)
        serializer = BusinessnearbySerializer(businesses, many=True)
        return Response(serializer.data)

#get busiensses
@api_view(['POST'])
def business(request):
    business_type = request.query_params.get('type', None)

    if business_type:
        query = "SELECT * FROM businesses WHERE businessType = %s"
        businesses = Business.objects.raw(query, [business_type])
    else:
        query = "SELECT * FROM businesses"
        businesses = Business.objects.raw(query)

    serializer = BusinessSerializer(businesses, many=True)
    return Response(serializer.data, status=status.HTTP_200_OK)

#get menu items
@api_view(['POST'])
def MenuItemsView(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id", None)
        
        if business_id:
            query = "SELECT * FROM menuItems WHERE business_id = %s"
            menu_items = MenuItems.objects.raw(query, [business_id])
        else:
            query = "SELECT * FROM menuItems"
            menu_items = MenuItems.objects.raw(query)

        serializer = MenuItemsSerializer(menu_items, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

#get product items
@api_view(['POST'])
def productItemsView(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id", None)
        
        if business_id:
            query = "SELECT * FROM Groceries WHERE business_id = %s"
            product_items = productItems.objects.raw(query, [business_id])
        else:
            query = "SELECT * FROM Groceries"
            product_items = productItems.objects.raw(query)

        serializer = productItemsSerializer(product_items, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

#add to cart for restaurants
@api_view(['POST'])
def AddToCartViewRES(request):
    user_id = request.GET.get("user_id")
    business_id = request.GET.get("business_id")
    item_id = request.data.get("item_id")
    quantity = int(request.data.get("quantity", 1))

    if not user_id or not business_id:
        return JsonResponse({"error": "user_id and business_id are required in URL params"}, status=400)

    try:
        user_id = int(user_id)
        item_id = int(item_id)
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": "Invalid ID format", "details": str(e)}, status=400)

    # 1. Fetch item details (use raw SQL instead of ORM)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT item_id, item_name, description, selling_price, availability_timings
            FROM menuItems 
            WHERE item_id=%s AND business_id=%s AND is_active=1 AND status=1
            """,
            [item_id, business_id],
        )
        menu_item = cursor.fetchone()

    if not menu_item:
        return JsonResponse({"error": "Menu item not found or inactive"}, status=404)

    item_id, item_name, description, selling_price, availability_timings = menu_item

    # 2. Check availability timings
    today = now().strftime("%a").lower()[:3]   # mon, tue, wed...
    current_time = now().strftime("%H:%M")

    availability = {}
    if availability_timings:
        try:
            availability = json.loads(availability_timings)  # parse string to dict
        except json.JSONDecodeError:
            availability = {}

    available_today = availability.get(today, [])

    is_available = any(
        slot.get("open") <= current_time <= slot.get("close") for slot in available_today
    )

    if not is_available:
        return JsonResponse({"error": "Item is not available in this moment"}, status=400)

    # 3. Insert or Update cart in one block
    with connection.cursor() as cursor:
        # Check if item already in cart
        cursor.execute(
            "SELECT id, quantity FROM menuCart WHERE user_id=%s AND business_id=%s AND menu_id=%s",
            [user_id, business_id, item_id],
        )
        row = cursor.fetchone()

        if row:  # Update quantity
            cart_id, existing_qty = row
            new_qty = existing_qty + quantity
            cursor.execute(
                "UPDATE menuCart SET quantity=%s, updated_at=NOW() WHERE id=%s",
                [new_qty, cart_id],
            )
            message = "Menu Cart increased with quantity"
        else:  # Insert new
            cursor.execute("SELECT COALESCE(MAX(id), 1100) + 1 FROM menuCart")
            new_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO menuCart (id, user_id, menu_id, quantity, business_id, added_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                [new_id, user_id, item_id, quantity, business_id],
            )
            cart_id, new_qty = new_id, quantity
            message = "Menu added to cart successfully"

    # 4. Build response (item details)
    item_details = {
        "item_id": item_id,
        "item_name": item_name,
        "description": description,
        "selling_price": str(selling_price),
        "quantity": new_qty,
    }

    # 5. Fetch all cart items (optimized)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, c.menu_id, c.quantity, m.item_name, m.description, m.selling_price
            FROM menuCart c
            JOIN menuItems m ON c.menu_id = m.item_id
            WHERE c.user_id=%s AND c.business_id=%s
            """,
            [user_id, business_id],
        )
        cart_rows = cursor.fetchall()

    menu_details = [
        {
            "cart_id": r[0],
            "item_id": r[1],
            "quantity": r[2],
            "item_name": r[3],
            "description": r[4],
            "selling_price": str(r[5]),
        }
        for r in cart_rows
    ]

    return JsonResponse({
        "message": message,
        "item_details": item_details,
        "menu_details": menu_details
    }, status=200)

#add to cart for restaurants
@api_view(['POST'])
def AddToCartViewGROCERY(request):
    user_id = request.GET.get("user_id")
    business_id = request.GET.get("business_id")
    item_id = request.data.get("item_id")
    quantity = int(request.data.get("quantity", 1))

    if not user_id or not business_id:
        return JsonResponse({"error": "user_id and business_id are required in URL params"}, status=400)

    try:
        user_id = int(user_id)
        item_id = int(item_id)
    except (ValueError, TypeError) as e:
        return JsonResponse({"error": "Invalid ID format", "details": str(e)}, status=400)

    # 1. Fetch item details (use raw SQL instead of ORM)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT item_id, item_name, description, selling_price, availability_timings
            FROM Groceries 
            WHERE item_id=%s AND business_id=%s AND is_active=1 AND status=1
            """,
            [item_id, business_id],
        )
        menu_item = cursor.fetchone()

    if not menu_item:
        return JsonResponse({"error": "Menu item not found or inactive"}, status=404)

    item_id, item_name, description, selling_price, availability_timings = menu_item

    # 2. Check availability timings
    # availability_timings is a datetime.time object or None
    if availability_timings:
        current_time = now().time()
        is_available = current_time >= availability_timings
    else:
        is_available = True  # If no availability set, assume always available

    if not is_available:
        return JsonResponse({"error": "This grocery item is not available at this time"}, status=400)

    # 3. Insert or Update cart in one block
    with connection.cursor() as cursor:
        # Check if item already in cart
        cursor.execute(
            "SELECT id, quantity FROM Groceries_cart WHERE user_id=%s AND business_id=%s AND item_id=%s",
            [user_id, business_id, item_id],
        )
        row = cursor.fetchone()

        if row:  # Update quantity
            cart_id, existing_qty = row
            new_qty = existing_qty + quantity
            cursor.execute(
                "UPDATE Groceries_cart SET quantity=%s, updated_at=NOW() WHERE id=%s",
                [new_qty, cart_id],
            )
            message = "Menu Cart increased with quantity"
        else:  # Insert new
            cursor.execute("SELECT COALESCE(MAX(id), 1100) + 1 FROM Groceries_cart")
            new_id = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO Groceries_cart (id, user_id, item_id, quantity, business_id, added_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                """,
                [new_id, user_id, item_id, quantity, business_id],
            )
            cart_id, new_qty = new_id, quantity
            message = "Menu added to cart successfully"

    # 4. Build response (item details)
    item_details = {
        "item_id": item_id,
        "item_name": item_name,
        "description": description,
        "selling_price": str(selling_price),
        "quantity": new_qty,
    }

    # 5. Fetch all cart items (optimized)
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, c.item_id, c.quantity, m.item_name, m.description, m.selling_price
            FROM Groceries_cart c
            JOIN Groceries m ON c.item_id = m.item_id
            WHERE c.user_id=%s AND c.business_id=%s
            """,
            [user_id, business_id],
        )
        cart_rows = cursor.fetchall()

    menu_details = [
        {
            "cart_id": r[0],
            "item_id": r[1],
            "quantity": r[2],
            "item_name": r[3],
            "description": r[4],
            "selling_price": str(r[5]),
        }
        for r in cart_rows
    ]

    return JsonResponse({
        "message": message,
        "item_details": item_details,
        "menu_details": menu_details
    }, status=200)
