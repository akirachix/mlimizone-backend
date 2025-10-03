from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.http import HttpResponse 
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator

from .models import ProduceListing, Cart, Order, Payment, MarketPrice, Crop, SMSLogs
from .serializers import (
    ProduceListingSerializer, CartSerializer, OrderSerializer,
    PaymentSerializer, MarketPriceSerializer, CropSerializer
)
from .permissions import (
    FarmerListingPermission, WholesalerCartPermission,
    OrderPermission, PaymentPermission, IsProjectAdmin
)
from .sms import send_sms
import logging

logger = logging.getLogger(__name__)

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

@method_decorator(csrf_exempt, name='dispatch')
class PaymentCallbackView(APIView):
    authentication_classes = [] 
    permission_classes = []     

    def get(self, request):
        return HttpResponse("M-Pesa Callback Endpoint Active. POST only.", content_type="text/plain")

    def post(self, request):
        logger.info(f"Incoming M-Pesa callback data: {request.data}")

        try:
            stk_callback = request.data.get('Body', {}).get('stkCallback', {})
            checkout_id = stk_callback.get('CheckoutRequestID')
            result_code = stk_callback.get('ResultCode')
            result_desc = stk_callback.get('ResultDesc', 'No description')

            if not checkout_id:
                logger.error("Missing CheckoutRequestID in callback")
                return HttpResponse("OK") 

            payment = Payment.objects.filter(transaction_ref=checkout_id).first()
            if not payment:
                logger.warning(f"Payment with CheckoutRequestID {checkout_id} not found")
                return HttpResponse("OK")

            if result_code == 0:
                payment.payment_status = 'completed'
                payment.order.status = 'paid'
                payment.order.save()

                message_body = f"Payment of {payment.amount} MWK for order {payment.order.order_id} confirmed."
                sms_response = send_sms(payment.order.wholesaler.phone_number, message_body)
                SMSLogs.objects.create(
                    user=payment.order.wholesaler,
                    message_body=message_body,
                    status='delivered' if sms_response.get('status_code') == 200 else 'failed'
                )

                farmer_message = (
                    f"Payment of {payment.amount} MWK for "
                    f"{payment.order.croplisting.quantity} KG of "
                    f"{payment.order.croplisting.crop.crop_name} confirmed."
                )
                farmer_sms = send_sms(payment.order.croplisting.farmer.phone_number, farmer_message)
                SMSLogs.objects.create(
                    user=payment.order.croplisting.farmer,
                    message_body=farmer_message,
                    status='delivered' if farmer_sms.get('status_code') == 200 else 'failed'
                )
            else:
                payment.payment_status = 'failed'
                logger.warning(f"Payment failed: {result_code} - {result_desc}")

            payment.save()
            logger.info(f"Payment {checkout_id} updated to status: {payment.payment_status}")

        except Exception as e:
            logger.error(f"Error processing M-Pesa callback: {str(e)}", exc_info=True)

        return HttpResponse("OK")