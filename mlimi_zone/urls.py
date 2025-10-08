from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (  ProduceListingViewSet,  CartViewSet,  OrderViewSet,  PaymentViewSet,  MarketPriceViewSet,  CropViewSet,  PaymentCallbackView )
from .ussd import USSDView

app_name = 'mlimi_zone'

router = DefaultRouter()
router.register(r'croplistings', ProduceListingViewSet)
router.register(r'carts', CartViewSet)
router.register(r'orders', OrderViewSet)
router.register(r'payments', PaymentViewSet)
router.register(r'marketprices', MarketPriceViewSet)
router.register(r'crops', CropViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('payment/callback/', PaymentCallbackView.as_view(), name='payment_callback'),
    path('ussd/', USSDView.as_view(), name='ussd'),
]