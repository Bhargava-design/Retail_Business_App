from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import business, MenuItemsView, productItemsView, nearby_businesses, AddToCartViewRES, AddToCartViewGROCERY
from .combine import (ItemsViewBasedonBusinessID, AddToCartViewBasedonBusinessID,
get_cart_items, update_cart_quantity)
from .orders import (
    create_order, update_order_status, get_order_details, list_user_orders, get_order_analytics
)
from .wallet import (
    get_wallet_balance, get_wallet_transactions, spend_wallet_points, list_available_coupons,
    validate_coupon, purchase_coupon_with_points, get_user_purchased_coupons, add_wallet_points
)
from .delivery import (
    calculate_delivery_charges, get_delivery_zones, create_delivery_configuration,
    check_delivery_availability, get_delivery_time_estimate
)

urlpatterns = [
    #-----------combined global code-----------
    
    #fetch the list of items based on business id
    path('items', ItemsViewBasedonBusinessID, name='fetch_items'), 
    
    #cart management globally based on business id
    path('add-to-cart', AddToCartViewBasedonBusinessID, name='add_to_cart'), #add items to the cart based on business id
    path('viewcart', get_cart_items, name='viewcart'), #view the cart items
    path('update-cart-quantity', update_cart_quantity, name='update_cart_quantity'), #update the cart quantity
    
    #-----------Basic Code-----------

    # Business and Items Individually
    path('business/', business, name='fetch_businesses'), #fetch the list of businesses
    path('nearby-businesses/', nearby_businesses, name='nearby-businesses'), #fetch the list of nearby businesses
    path('menu-items', MenuItemsView, name='fetch_menu_items'), #fetch the list of menu items
    path('product-items', productItemsView, name='fetch_product_items'), #fetch the list of product items
    
    # Cart Management Individually
    path('res/add-to-cart', AddToCartViewRES, name='add_to_cart_res'), #add items to the cart
    path('grocery/add-to-cart', AddToCartViewGROCERY, name='add_to_cart_grocery'), #add grocery items to the cart

    # Spend walllet points or coupons before placing the order
    path('coupons/validate/', validate_coupon, name='validate_coupon'), #validate the coupon code for specific order context``
    path('wallet/spend/', spend_wallet_points, name='spend_wallet_points'), # spend some points while ordering the items
    
    #create order here with or without coupons and wallet points
    path('orders/create/', create_order, name='create_order'), 

    # payment gateway setup


    # order management 
    path('orders/<int:order_id>/status/', update_order_status, name='update_order_status'), #change the status of an order
    path('orders/user/<int:user_id>/', list_user_orders, name='list_user_orders'), #display the list of orders
    path('orders/<int:order_id>/', get_order_details, name='get_order_details'), # display the detail view of each order
    path('orders/analytics/', get_order_analytics, name='get_order_analytics'), #dispaly the order analytics of each user order

    # Wallet Management
    path('wallet/add/', add_wallet_points, name='add_wallet_points'), # add some points to the wallet
    path('wallet/<int:user_id>/', get_wallet_balance, name='get_wallet_balance'), #check the balance of your wallet points
    path('wallet/<int:user_id>/transactions/', get_wallet_transactions, name='get_wallet_transactions'), #get your transaction history of wallet points
    
    # Coupon Management
    path('coupons/available/', list_available_coupons, name='list_available_coupons'), #display the list of available coupons
    path('coupons/purchase/', purchase_coupon_with_points, name='purchase_coupon_with_points'), #purchase the coupon with points
    path('coupons/user/<int:user_id>/', get_user_purchased_coupons, name='get_user_purchased_coupons'), #display the list of purchased coupons

    # Delivery Management
    path('delivery/calculate/', calculate_delivery_charges, name='calculate_delivery_charges'),
    path('delivery/zones/<int:business_id>/', get_delivery_zones, name='get_delivery_zones'),
    path('delivery/config/', create_delivery_configuration, name='create_delivery_configuration'),
    path('delivery/availability/', check_delivery_availability, name='check_delivery_availability'),
    path('delivery/estimate/', get_delivery_time_estimate, name='get_delivery_time_estimate'),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)