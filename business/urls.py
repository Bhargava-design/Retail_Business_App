# urls.py
from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .views import ( 
    fetchbusinessesTypes,
    fetchbusinessFeatures,
    CreateBusinessAPIView,
    CreateMenuItemsAPIView,
    MenuItemsManagementAPIView,
    addBOMItems, addProductItems,
    BOMItemsManagementAPIView, 
    updateProductItems,
    menuDetailView, productDetailView
)
from .coupons import (
    create_coupon, list_business_coupons, update_coupon, delete_coupon, add_coupon_rule, coupon_analytics, get_user_businesses
)
from .delivery import (
    configure_delivery_charges,
    get_delivery_configuration,
    configure_points_system,
    get_points_configuration
)
from .payment import payment_gateway, save_payment_data, process_refund

urlpatterns = [
    #fetch to create business
    path('fetch-types/', fetchbusinessesTypes, name='fetch_businesses'), #featches the business Types
    path('business-features/', fetchbusinessFeatures, name='fetch_business_Features'), #fetches the business features

    #create business service
    path('create', CreateBusinessAPIView, name='CreateBusinessAPIView'), #create the business in 3 sections
    path('payment-gateway/', payment_gateway, name='payment_gateway'), #calls the paymnet Gatway html page to create a busienss
    path('save-payment-data/', save_payment_data, name='save_payment_data'), #save payment details while creating the business
    path('process-refund/', process_refund, name='process_refund'), # currently no need refunding the payment if they don't want

    #display the busienss details for the user businesses
    path('user-businesses/', get_user_businesses, name='get_user_businesses'),
    
    #create menu items
    path('add-menu-items', CreateMenuItemsAPIView, name='CreateMenuItemsAPIView'),  #add menu items here by busienss owners
    path('menu-items-management/<int:item_id>/', MenuItemsManagementAPIView, name='MenuItemsManagementAPIView'), # update the menu items here
    path('add-bom-items', addBOMItems, name='addBOMItems'), # add ingredients here for your menu items
    path('bom-items-management/', BOMItemsManagementAPIView, name='BOMItemsManagementAPIView'), #Manage your ingredients here 

    #create product items
    path('add-product-items', addProductItems, name='addProductItems'), # add product items for your grocery business
    path('product-items-management/<int:item_id>/', updateProductItems, name='updateProductItems'), #update the grocery items that owner want to sell
    
    #detail views
    path('menu/detail-view', menuDetailView, name='menuDetailView'), #dispaly the detail view of menu items here before update
    path('product/detail-view', productDetailView, name='productDetailView'), # display the detail view of product items before update
    
    # Coupon Management APIs
    path('create-coupon/', create_coupon, name='create_coupon'), # to create a coupon for your business
    path('coupons/<int:coupon_id>/rules/', add_coupon_rule, name='add_coupon_rule'), #add the coupon rule using this
    path('coupons/', list_business_coupons, name='list_business_coupons'), # display the list of coupons for your business
    path('coupons/<int:coupon_id>/', update_coupon, name='update_coupon'), # update your coupons here for your business
    # path('coupons/<int:coupon_id>/toggle/', toggle_coupon_status, name='toggle_coupon_status'), #currently no need, activate or deactive your coupon using it
    path('coupons/<int:coupon_id>/delete/', delete_coupon, name='delete_coupon'), #delete the coupon permenantely using this 
    path('coupon-analytics/', coupon_analytics, name='coupon_analytics'), #See the coupon analytics using this 
    
    # Delivery management by business owners
    path('configure-delivery/', configure_delivery_charges, name='configure_delivery_charges'), # add the delivery configuration for your business here
    path('delivery-config/', get_delivery_configuration, name='get_delivery_configuration'), #display the delivery configurations of your business
    #need update the delivery configuration and delete delivery configuration services

    #Wallet points management by business owners
    path('configure-points/', configure_points_system, name='configure_points_system'), #give points to the users from your business
    path('points-config/', get_points_configuration, name='get_points_configuration'), # display the points that you want to give to the user from your business
    #need update the points, make it active or inactive the points and delete the points configuration
    
]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)