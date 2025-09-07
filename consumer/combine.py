from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
from business.models import MenuItems, productItems
from consumer.serializers import MenuItemsSerializer, productItemsSerializer
from django.db import connection
from rest_framework.response import Response
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import datetime, json
from .models import MenuCart, GrocerieCart
#Display Menu Items
@api_view(['POST'])
def ItemsViewBasedonBusinessID(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id", None)
        business_type = request.query_params.get("type", None)  # Get businessType from params

        if not business_type:
            return Response({"error": "businessType is required"}, status=status.HTTP_400_BAD_REQUEST)

        # For Restaurants (R02) → MenuItems 
        if business_type == "R02":
            if business_id:
                query = "SELECT * FROM menuItems WHERE business_id = %s"
                items = MenuItems.objects.raw(query, [business_id])
            else:
                query = "SELECT * FROM menuItems"
                items = MenuItems.objects.raw(query)
            serializer = MenuItemsSerializer(items, many=True)

        # For Groceries (R01) → productItems
        elif business_type == "R01":
            if business_id:
                query = "SELECT * FROM Groceries WHERE business_id = %s"
                items = productItems.objects.raw(query, [business_id])
            else:
                query = "SELECT * FROM Groceries"
                items = productItems.objects.raw(query)
            serializer = productItemsSerializer(items, many=True)

        else:
            return Response({"error": "Invalid businessType"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(serializer.data, status=status.HTTP_200_OK)

#Add to Cart
@api_view(['POST'])
def AddToCartViewBasedonBusinessID(request):
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

    # 1. Get business type
    with connection.cursor() as cursor:
        cursor.execute("SELECT businessType FROM businesses WHERE business_id=%s", [business_id])
        row = cursor.fetchone()

    if not row:
        return JsonResponse({"error": "Business not found"}, status=404)

    business_type = row[0]

    # ---------------- CASE R02 (Restaurants) ---------------- #
    if business_type == "R02":
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

        # Availability check
        today = now().strftime("%a").lower()[:3]
        current_time = now().strftime("%H:%M")

        availability = availability_timings or {}
        available_today = availability.get(today, [])
        is_available = any(slot["open"] <= current_time <= slot["close"] for slot in available_today)

        if not is_available:
            return JsonResponse({"error": "Item is not available in this moment"}, status=400)

        # Insert/Update menuCart
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, quantity FROM menuCart WHERE user_id=%s AND business_id=%s AND menu_id=%s",
                [user_id, business_id, item_id],
            )
            row = cursor.fetchone()

            if row:
                cart_id, existing_qty = row
                new_qty = existing_qty + quantity
                cursor.execute("UPDATE menuCart SET quantity=%s, updated_at=NOW() WHERE id=%s", [new_qty, cart_id])
                message = "Menu Cart increased with quantity"
            else:
                cursor.execute("SELECT COALESCE(MAX(id), 1100) + 1 FROM menuCart")
                new_id = cursor.fetchone()[0]
                cursor.execute(
                    """
                    INSERT INTO menuCart (id, user_id, menu_id, quantity, business_id, added_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    """,
                    [new_id, user_id, item_id, quantity, business_id],
                )
                new_qty = quantity
                message = "Menu added to cart successfully"

        item_details = {
            "item_id": item_id,
            "item_name": item_name,
            "description": description,
            "selling_price": str(selling_price),
            "quantity": new_qty,
        }

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

        return JsonResponse({"message": message, "item_details": item_details, "menu_details": menu_details}, status=200)

    # ---------------- CASE R01 (Groceries) ---------------- #
    elif business_type == "R01":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT item_id, item_name, description, selling_price
                FROM Groceries
                WHERE item_id=%s AND business_id=%s AND is_active=1 AND status=1
                """,
                [item_id, business_id],
            )
            grocery_item = cursor.fetchone()

        if not grocery_item:
            return JsonResponse({"error": "Grocery item not found or inactive"}, status=404)

        item_id, item_name, description, selling_price = grocery_item

        # Insert/Update Groceries_cart
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT id, quantity FROM Groceries_cart WHERE user_id=%s AND business_id=%s AND item_id=%s",
                [user_id, business_id, item_id],
            )
            row = cursor.fetchone()

            if row:
                cart_id, existing_qty = row
                new_qty = existing_qty + quantity
                cursor.execute("UPDATE Groceries_cart SET quantity=%s, updated_at=NOW() WHERE id=%s", [new_qty, cart_id])
                message = "Groceries Cart increased with quantity"
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
                message = "Grocery item added to cart successfully"

        item_details = {
            "item_id": item_id,
            "item_name": item_name,
            "description": description,
            "selling_price": str(selling_price),
            "quantity": new_qty,
        }

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT c.id, c.item_id, c.quantity, g.item_name, g.description, g.selling_price
                FROM Groceries_cart c
                JOIN Groceries g ON c.item_id = g.item_id
                WHERE c.user_id=%s AND c.business_id=%s
                """,
                [user_id, business_id],
            )
            cart_rows = cursor.fetchall()

        groceries_details = [
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

        return JsonResponse({"message": message, "item_details": item_details, "groceries_details": groceries_details}, status=200)

    else:
        return JsonResponse({"error": f"Unsupported business type {business_type}"}, status=400)

#Get Cart Items
@csrf_exempt
def get_cart_items(request):
    if request.method != "POST":
        return JsonResponse({"message": "Invalid request method. Use POST"}, status=405)

    user_id = request.GET.get("user_id")
    cart_type = request.GET.get("type")  # Optional: R01 / R02

    if not user_id:
        return JsonResponse({"message": "user_id parameter is required"}, status=400)

    if cart_type == "R01":
        # Groceries cart
        query = """
            SELECT 
                c.id,            -- cart id
                c.item_id,
                c.quantity,
                g.item_name,
                g.description,
                g.selling_price
            FROM Groceries_cart c
            JOIN Groceries g ON c.item_id = g.item_id
            WHERE c.user_id = %s
        """
    elif cart_type == "R02":
        # Menu cart
        query = """
            SELECT 
                c.id,            -- cart id
                c.menu_id,
                c.quantity,
                m.item_name,
                m.description,
                m.selling_price
            FROM menuCart c
            JOIN menuItems m ON c.menu_id = m.item_id   -- ✅ match correctly
            WHERE c.user_id = %s
        """
    else:
        return JsonResponse({"message": "Invalid type. Use R01 for groceries or R02 for menu"}, status=400)

    with connection.cursor() as cursor:
        cursor.execute(query, [user_id])
        rows = cursor.fetchall()

    if not rows:
        return JsonResponse({"message": "Cart is Empty please add the items in the cart"}, status=200)

    menu_details = []
    for row in rows:
        menu_details.append({
            "cart_id": row[0],       # cart primary key (id)
            "item_id": row[1],       # item_id for groceries / menu_id for menuCart
            "quantity": row[2],
            "item_name": row[3],
            "description": row[4],
            "selling_price": str(row[5])
        })

    return JsonResponse({"menu_details": menu_details}, status=200, safe=False)

@csrf_exempt
@api_view(['POST'])
def update_cart_quantity(request):
    """
    Update quantity of cart items
    URL: POST /update-cart-quantity?id={cart_id}&type=R01&action=inc/dec
    """
    cart_id = request.GET.get("id")
    cart_type = request.GET.get("type")  # R01 -> groceries, R02 -> menu
    action = request.GET.get("action")   # "inc" or "dec"

    if not cart_id or not cart_type or not action:
        return JsonResponse({"message": "id, type, and action are required"}, status=400)

    try:
        if cart_type == "R01":
            cart_item = GrocerieCart.objects.get(id=cart_id)
        elif cart_type == "R02":
            cart_item = MenuCart.objects.get(id=cart_id)
        else:
            return JsonResponse({"message": "Invalid type. Use R01 or R02"}, status=400)

    except (GrocerieCart.DoesNotExist, MenuCart.DoesNotExist):
        return JsonResponse({"message": "Cart item not found"}, status=404)

    if action == "inc":
        cart_item.quantity += 1
        cart_item.save()
        return JsonResponse({"message": "Quantity increased", "quantity": cart_item.quantity}, status=200)

    elif action == "dec":
        if cart_item.quantity > 1:
            cart_item.quantity -= 1
            cart_item.save()
            return JsonResponse({"message": "Quantity decreased", "quantity": cart_item.quantity}, status=200)
        else:
            cart_item.delete()
            return JsonResponse({"message": "Item removed from cart"}, status=200)

    else:
        return JsonResponse({"message": "Invalid action. Use inc or dec"}, status=400)

