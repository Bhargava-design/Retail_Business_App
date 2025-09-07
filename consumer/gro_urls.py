from django.urls import path
from django.conf import settings
from django.conf.urls.static import static
from .gro_views import (
    GroceriesByBusinessView, 
    GroceryCategoriesByBusinessView, 
    GroceriesByCategoryView, 
    GroceriesCartView, 
    CreateOrderView, 
    OrderDetailsView, 
    CreatePaymentView, 
    VerifyPaymentView, 
    HighRatedProductsView,
    GroceryPartnerRegistrationView,
    AssignOrderToPartnerView,
    PartnerAssignedOrdersView
)

urlpatterns = [
    
    path('product-items/', GroceriesByBusinessView.as_view(), name='product-items-by-business'),
    path('grocery-categories/', GroceryCategoriesByBusinessView.as_view(), name='grocery-categories-by-business'),
    path('groceries-by-category/', GroceriesByCategoryView.as_view(), name='groceries-by-category'),

    # Cart URL (uses query parameters)
    path('cart/', GroceriesCartView.as_view(), name='cart-operations'),

    # Order URL
    path('create-order/', CreateOrderView.as_view(), name='create-order'),
    path('order-details/', OrderDetailsView.as_view(), name='order-details'),

    # Razorpay Payment URLs
    path('create-razorpay-order/', CreatePaymentView.as_view(), name='create-razorpay-order'),
    path('verify-razorpay-payment/', VerifyPaymentView.as_view(), name='verify-razorpay-payment'),
    
    # High-rated products URL
    path('high-rated-products/', HighRatedProductsView.as_view(), name='high-rated-products'),
    
    # Partner registration URL (uses query parameters for user_id and business_id)
    path('partner-registration/', GroceryPartnerRegistrationView.as_view(), name='partner-registration'),
    
    # Delivery assignment URLs
    path('assign-order/', AssignOrderToPartnerView.as_view(), name='assign-order-to-partner'),
    path('partner-orders/', PartnerAssignedOrdersView.as_view(), name='partner-assigned-orders'),

]+ static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)