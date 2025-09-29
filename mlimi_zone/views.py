from rest_framework import viewsets, status
from rest_framework.response import Response
from .models import ProduceListing, Cart, Order, Payment, MarketPrice, Crop
from .serializers import ProduceListingSerializer, CartSerializer, OrderSerializer, PaymentSerializer, MarketPriceSerializer, CropSerializer
from .permissions import FarmerListingPermission, WholesalerCartPermission, OrderPermission, PaymentPermission, IsProjectAdmin
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny

class ProduceListingViewSet(viewsets.ModelViewSet):
    queryset = ProduceListing.objects.all()
    serializer_class = ProduceListingSerializer
    permission_classes = [FarmerListingPermission]
    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'farmer':
            return ProduceListing.objects.filter(farmer=user)
        return super().get_queryset()
    
class CartViewSet(viewsets.ModelViewSet):
    queryset = Cart.objects.all()
    serializer_class = CartSerializer
    permission_classes = [WholesalerCartPermission]
    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'wholesaler':
            return Cart.objects.filter(wholesaler=user)
        return Cart.objects.none()
    def destroy(self, request, *args, **kwargs):
        return Response({'detail': 'Cart deletion not allowed.'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
    
class OrderViewSet(viewsets.ModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [OrderPermission]
    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'wholesaler':
            return Order.objects.filter(wholesaler=user)
        if getattr(user, 'role', None) == 'farmer':
            return Order.objects.filter(croplisting__farmer=user)
        return Order.objects.none()
    
class PaymentViewSet(viewsets.ModelViewSet):
    queryset = Payment.objects.all()
    serializer_class = PaymentSerializer
    permission_classes = [PaymentPermission]
    def get_queryset(self):
        user = self.request.user
        if getattr(user, 'role', None) == 'wholesaler':
            return Payment.objects.filter(order__wholesaler=user)
        if getattr(user, 'role', None) == 'farmer':
            return Payment.objects.filter(order__croplisting__farmer=user)
        return Payment.objects.none()
    

class MarketPriceViewSet(viewsets.ModelViewSet):
    queryset = MarketPrice.objects.all()
    serializer_class = MarketPriceSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsProjectAdmin()]

class CropViewSet(viewsets.ModelViewSet):
    queryset = Crop.objects.all()
    serializer_class = CropSerializer

    def get_permissions(self):
        if self.action in ['list', 'retrieve']:
            return [AllowAny()]
        return [IsProjectAdmin()]








