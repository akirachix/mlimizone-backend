from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ProduceListingViewSet, CartViewSet, OrderViewSet, PaymentViewSet, MarketPriceViewSet, CropViewSet

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
]
