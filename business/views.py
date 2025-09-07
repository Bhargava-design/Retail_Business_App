# views.py
from requests import api
from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.response import Response
from kirazee_app.models import BusinessType, BusinessFeature, Business, BusinessMapping, Registration, BusinessOwnerDetails
from .serializers import (
        BusinessTypeSerializer, 
        BusinessFeatureSerializer, 
        Businesssection1serializers, 
        Businesssection2Serializer, 
        Businesssection3Serializer,
        MenuItemsSerializer, 
        BOMSerializer, productItemsSerializer
        )
from .models import MenuItems, BOM, BillOfMaterialsLog, productItems
import json

@api_view(['GET'])  # Allow only GET requests
def fetchbusinessesTypes(request):
    if request.method == 'GET':
        business_types = BusinessType.objects.filter(status=True)
        serializer = BusinessTypeSerializer(business_types, many=True)
        return Response(serializer.data)
    # Optional fallback for unsupported methods
    return Response({"error": "Method not allowed"}, status=405)

@api_view(['GET'])
def fetchbusinessFeatures(request):
    if request.method == 'GET':
        business_feature = BusinessFeature.objects.filter(status=True)
        serializer = BusinessFeatureSerializer(business_feature, many=True)
        return Response(serializer.data)
    return Response({"error": "Method not allowed"}, status=405)

@api_view(['POST'])
def CreateBusinessAPIView(request):
    if request.method == 'POST':
        user_id = request.query_params.get("userID")
        section = request.query_params.get("section")

        if not user_id or not section:
            return Response({"error": "userID and section are required"}, status=status.HTTP_400_BAD_REQUEST)

        # SECTION 1
        if section == "1":
            serializer = Businesssection1serializers(data=request.data, context={"user_id": user_id, "request": request})
            if serializer.is_valid():
                business = serializer.save()
                return Response(
                    {"message": "Business created successfully", "business_id": business.business_id, "business_details": serializer.data},
                    status=status.HTTP_201_CREATED
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # SECTION 2
        if section == "2":
            business_id = request.data.get("business_id")
            if not business_id:
                return Response({"error": "business_id is required for section 2"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                business = Business.objects.get(business_id=business_id, status=True)
            except Business.DoesNotExist:
                return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

            serializer = Businesssection2Serializer(business, data=request.data, partial=True)
            if serializer.is_valid():
                updated_business = serializer.save()
                return Response(
                    {"message": "Business address & location added successfully", "business_id": updated_business.business_id,
                    "business_details": serializer.data},
                    status=status.HTTP_200_OK
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        # SECTION 3
        if section == "3":
            serializer = Businesssection3Serializer(data=request.data)  # request.data is already parsed dict
            if serializer.is_valid():
                financial = serializer.save()
                return Response(
                    {"message": "Business financial details added successfully", "business_id": financial.business_id,
                    "financial_details": serializer.data},
                    status=status.HTTP_201_CREATED
                )
            else:
                return Response(serializer.errors)

        return Response({"error": "Invalid section"}, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def CreateMenuItemsAPIView(request):
    if request.method == 'POST':
        user_id = request.query_params.get("userID")
        business_id = request.query_params.get("business_id")

        if not user_id or not business_id:
            return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        # Validate user exists and is active
        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)
        
        # Validate business exists and is active
        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
        
        # Check if user has access to this business
        if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)
        
        # Create menu item
        serializer = MenuItemsSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            # Set the business_id for the menu item
            serializer.validated_data['business_id'] = business
            menu_item = serializer.save()
            return Response({
                "message": "Menu item created successfully",
                "item_id": menu_item.item_id,
                "menu_item_details": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'PATCH', 'DELETE'])
def MenuItemsManagementAPIView(request, item_id):
    user_id = request.query_params.get("userID")
    business_id = request.query_params.get("business_id")
    menu_item = request.query_params.get("item_id")

    if not user_id or not business_id:
        return Response({"error": "userID and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)
    
    # Validate user exists and is active
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid userID"}, status=status.HTTP_404_NOT_FOUND)
    
    # Validate business exists and is active
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
    
    # Check if user has access to this business
    if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
        return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)
    
    # Get the menu item
    try:
        menu_item = MenuItems.objects.get(item_id=item_id, business_id=business)
    except MenuItems.DoesNotExist:
        return Response({"error": "Menu item not found"}, status=status.HTTP_404_NOT_FOUND)
    
    # Handle DELETE request
    if request.method == 'DELETE':
        item_name = menu_item.item_name
        menu_item.delete()
        return Response({
            "message": f"Menu item '{item_name}' deleted successfully",
            "item_id": item_id
        }, status=status.HTTP_200_OK)
    
    # Handle PUT and PATCH requests (UPDATE)
    if request.method in ['PUT', 'PATCH']:
        # Prepare data for serializer
        data = request.data.copy()
        
        # Update menu item
        partial = request.method == 'PATCH'
        serializer = MenuItemsSerializer(menu_item, data=data, partial=partial, context={"request": request})
        if serializer.is_valid():
            updated_menu_item = serializer.save()
            
            # Get the serialized data with the image URL
            response_serializer = MenuItemsSerializer(updated_menu_item, context={"request": request})
            
            return Response({
                "message": "Menu item updated successfully",
                "item_id": updated_menu_item.item_id,
                "menu_item_details": response_serializer.data
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def addBOMItems(request):
    if request.method == 'POST':
        business_id = request.query_params.get("business_id")
        product_id = request.query_params.get("product_id")
        user_id = request.query_params.get("user_id")  # Add user_id for logging

        if not business_id or not product_id:
            return Response({"error": "business_id and product_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)

        # Check if menu item exists
        try:
            menu_item = MenuItems.objects.get(item_id=product_id)
        except MenuItems.DoesNotExist:
            return Response({"error": f"Menu item with ID {product_id} does not exist"}, status=status.HTTP_404_NOT_FOUND)

        # Check if menu item belongs to the business
        try:
            item = MenuItems.objects.get(item_id=product_id, business_id=business, status=True)
        except MenuItems.DoesNotExist:
            return Response({
                "error": f"Menu item {product_id} doesn't belong to business {business_id}",
                "debug_info": {
                    "requested_business_id": business_id,
                    "menu_item_business_id": menu_item.business_id.business_id,
                    "menu_item_status": menu_item.status
                }
            }, status=status.HTTP_404_NOT_FOUND)

        serializer = BOMSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            from django.db import transaction, connection
            
            try:
                with transaction.atomic():
                    # Save the BOM item first with default status = 1
                    bom = serializer.save(business_id=business, product_id=item)
                    bom.status = 1  # Set default status as active
                    bom.save()
                    
                    # Create log entry after BOM is created (satisfies FK constraint)
                    new_data = {
                        'bom_id': bom.bom_id,
                        'business_id': str(bom.business_id.business_id),
                        'product_id': bom.product_id.item_id,
                        'ingredients': bom.ingredients,
                        'quantity': str(bom.quantity),
                        'unit': bom.unit,
                        'cost': str(bom.cost),
                        'status': bom.status,
                        'created_at': bom.created_at.isoformat() if bom.created_at else None,
                        'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                    }
                    
                    # Create log entry with user_id
                    BillOfMaterialsLog.objects.create(
                        bom_id=bom.bom_id,
                        user_id=int(user_id) if user_id else None,
                        action_type='INSERT',
                        old_data=None,
                        new_data=new_data
                    )
                    
            except Exception as e:
                return Response({
                    "error": f"Failed to create BOM item: {str(e)}"
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            response_serializer = BOMSerializer(bom)
            return Response({
                "message": "BOM item added successfully",
                "bom_id": bom.bom_id,
                "bom_details": response_serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['PUT', 'PATCH', 'DELETE'])
def BOMItemsManagementAPIView(request):
    user_id = request.query_params.get("user_id")
    business_id = request.query_params.get("business_id")
    bom_id = request.query_params.get("bom_id")

    if not user_id or not business_id or not bom_id:
        return Response({"error": "user_id, business_id and bom_id are required"}, status=status.HTTP_400_BAD_REQUEST)

    try:
        bom = BOM.objects.get(bom_id=bom_id, business_id=business_id, status=1)
    except BOM.DoesNotExist:
        # Check if BOM exists but is soft deleted
        try:
            soft_deleted_bom = BOM.objects.get(bom_id=bom_id, business_id=business_id, status=0)
            return Response({"error": "BOM item is already deleted"}, status=status.HTTP_410_GONE)
        except BOM.DoesNotExist:
            return Response({"error": "Invalid bom_id"}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'PUT' or request.method == 'PATCH':
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Capture old data before update
                old_data = {
                    'bom_id': bom.bom_id,
                    'business_id': str(bom.business_id.business_id),
                    'product_id': bom.product_id.item_id,
                    'ingredients': bom.ingredients,
                    'quantity': str(bom.quantity),
                    'unit': bom.unit,
                    'cost': str(bom.cost),
                    'status': bom.status,
                    'created_at': bom.created_at.isoformat() if bom.created_at else None,
                    'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                }
                
                serializer = BOMSerializer(bom, data=request.data, partial=True)
                if serializer.is_valid():
                    updated_bom = serializer.save()
                    
                    # Capture new data after update
                    new_data = {
                        'bom_id': updated_bom.bom_id,
                        'business_id': str(updated_bom.business_id.business_id),
                        'product_id': updated_bom.product_id.item_id,
                        'ingredients': updated_bom.ingredients,
                        'quantity': str(updated_bom.quantity),
                        'unit': updated_bom.unit,
                        'cost': str(updated_bom.cost),
                        'status': updated_bom.status,
                        'created_at': updated_bom.created_at.isoformat() if updated_bom.created_at else None,
                        'updated_at': updated_bom.updated_at.isoformat() if updated_bom.updated_at else None
                    }
                    
                    # Create log entry for update
                    BillOfMaterialsLog.objects.create(
                        bom_id=updated_bom.bom_id,
                        user_id=int(user_id),
                        action_type='UPDATE',
                        old_data=old_data,
                        new_data=new_data
                    )
                    
                    return Response({
                        "message": "BOM item updated successfully",
                        "bom_id": updated_bom.bom_id,
                        "bom_details": serializer.data
                    }, status=status.HTTP_200_OK)
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
                
        except Exception as e:
            return Response({
                "error": f"Failed to update BOM item: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    elif request.method == 'DELETE':
        from django.db import transaction
        
        try:
            with transaction.atomic():
                # Prepare old_data for logging (before soft delete)
                old_data = {
                    'bom_id': bom.bom_id,
                    'business_id': str(bom.business_id.business_id),
                    'product_id': bom.product_id.item_id,
                    'ingredients': bom.ingredients,
                    'quantity': str(bom.quantity),
                    'unit': bom.unit,
                    'cost': str(bom.cost),
                    'status': bom.status,
                    'created_at': bom.created_at.isoformat() if bom.created_at else None,
                    'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                }
                
                # Perform soft delete by setting status = 0
                bom.status = 0
                bom.save()
                
                # Prepare new_data after soft delete
                new_data = {
                    'bom_id': bom.bom_id,
                    'business_id': str(bom.business_id.business_id),
                    'product_id': bom.product_id.item_id,
                    'ingredients': bom.ingredients,
                    'quantity': str(bom.quantity),
                    'unit': bom.unit,
                    'cost': str(bom.cost),
                    'status': bom.status,  # Now 0 (soft deleted)
                    'created_at': bom.created_at.isoformat() if bom.created_at else None,
                    'updated_at': bom.updated_at.isoformat() if bom.updated_at else None
                }
                
                # Create log entry for soft delete
                BillOfMaterialsLog.objects.create(
                    bom_id=bom.bom_id,
                    user_id=int(user_id),
                    action_type='DELETE',
                    old_data=old_data,
                    new_data=new_data
                )
                
        except Exception as e:
            return Response({
                "error": f"Failed to delete BOM item: {str(e)}"
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            "message": "BOM item deleted successfully (soft delete)",
            "bom_id": bom_id,
            "status": "inactive"
        }, status=status.HTTP_200_OK)

@api_view(['POST'])
def addProductItems(request):
    if request.method == 'POST':
        user_id = request.query_params.get("user_id")
        business_id = request.query_params.get("business_id")

        if not user_id or not business_id:
            return Response({"error": "user_id and business_id are required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = Registration.objects.get(user_id=user_id, status=True)
        except Registration.DoesNotExist:
            return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            business = Business.objects.get(business_id=business_id, status=True)
        except Business.DoesNotExist:
            return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
        
        if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
            return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)
        
        serializer = productItemsSerializer(data=request.data, context={"request": request})
        if serializer.is_valid():
            product_item = serializer.save(business_id=business)
            product_item.status = True  # Set default status as active (True = 1)
            product_item.is_active = True
            product_item.save()
            return Response({
                "message": "Product item added successfully",
                "item_id": product_item.item_id,
                "product_item_details": serializer.data
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def menuDetailView(request):
    if request.method == 'POST':
        menu_id = request.query_params.get("menu_id")
        
        if not menu_id:
            return Response({"error": "menu_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get menu item details
            menu_item = MenuItems.objects.get(item_id=menu_id)
        except MenuItems.DoesNotExist:
            return Response({"error": "Menu item not found or inactive"}, status=status.HTTP_404_NOT_FOUND)
        
        # Serialize menu item details
        menu_serializer = MenuItemsSerializer(menu_item, context={"request": request})
        
        # Get BOM details for this menu item
        bom_items = BOM.objects.filter(product_id=menu_id)
        bom_serializer = BOMSerializer(bom_items, many=True)
        
        return Response({
            "menu_details": menu_serializer.data,
            "BOM_details": bom_serializer.data
        }, status=status.HTTP_200_OK)

@api_view(['POST'])
def productDetailView(request):
    if request.method == 'POST':
        product_id = request.query_params.get("product_id")
        
        if not product_id:
            return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Get product item details
            product_item = productItems.objects.get(item_id=product_id)
        except productItems.DoesNotExist:
            return Response({"error": "Product item not found or inactive"}, status=status.HTTP_404_NOT_FOUND)
        
        # Serialize product item details
        product_serializer = productItemsSerializer(product_item, context={"request": request})
        
        # Get BOM details for this product item (if any)
        bom_items = BOM.objects.filter(product_id=product_id)
        bom_serializer = BOMSerializer(bom_items, many=True)
        
        return Response({
            "product_details": product_serializer.data,
            "BOM_details": bom_serializer.data
        }, status=status.HTTP_200_OK)

@api_view(['PUT', 'PATCH', 'DELETE'])
def updateProductItems(request, item_id):
    user_id = request.query_params.get("user_id")
    business_id = request.query_params.get("business_id")
    
    if not user_id or not business_id or not item_id:
        return Response({"error": "user_id, business_id and item_id are required"}, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        user = Registration.objects.get(user_id=user_id, status=True)
    except Registration.DoesNotExist:
        return Response({"error": "Invalid user_id"}, status=status.HTTP_404_NOT_FOUND)
    
    try:
        business = Business.objects.get(business_id=business_id, status=True)
    except Business.DoesNotExist:
        return Response({"error": "Invalid business_id"}, status=status.HTTP_404_NOT_FOUND)
    
    if not BusinessMapping.objects.filter(user_id=user_id, business_id=business_id).exists():
        return Response({"error": "User does not have access to this business"}, status=status.HTTP_403_FORBIDDEN)
    
    try:
        # First check if item exists at all
        product_item = productItems.objects.get(item_id=item_id)
        
        # Check if it belongs to the correct business
        if str(product_item.business_id.business_id) != str(business_id):
            return Response({
                "error": "Product item doesn't belong to this business",
                "debug_info": {
                    "item_business_id": str(product_item.business_id.business_id),
                    "requested_business_id": str(business_id)
                }
            }, status=status.HTTP_403_FORBIDDEN)
        
        # Check if item is active
        if not product_item.status:
            return Response({"error": "Product item is already deleted"}, status=status.HTTP_410_GONE)
            
    except productItems.DoesNotExist:
        return Response({"error": "Invalid item_id"}, status=status.HTTP_404_NOT_FOUND)
    
    if request.method == 'PUT' or request.method == 'PATCH':
        serializer = productItemsSerializer(product_item, data=request.data, partial=True)
        if serializer.is_valid():
            updated_product_item = serializer.save()
            return Response({
                "message": "Product item updated successfully",
                "item_id": updated_product_item.item_id,
                "product_item_details": serializer.data
            }, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    elif request.method == 'DELETE':
        product_item.status = False
        product_item.save()
        return Response({
            "message": "Product item deleted successfully",
            "item_id": product_item.item_id
        }, status=status.HTTP_200_OK)

