from rest_framework import serializers
from .models import ProduceListing, Cart, Order, Payment, MarketPrice, Crop, User
class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('user_id', 'name', 'phone_number', 'role', 'location', 'created_at')

class CropSerializer(serializers.ModelSerializer):
    class Meta:
        model = Crop
        fields = ('crop_id', 'crop_name')

class MarketPriceSerializer(serializers.ModelSerializer):
    crop = CropSerializer(read_only=True)
    crop_id = serializers.PrimaryKeyRelatedField(write_only=True, queryset=Crop.objects.all(), source='crop')
    class Meta:
        model = MarketPrice
        fields = ('market_price_id', 'crop', 'crop_id', 'location', 'price_per_unit', 'created_at', 'updated_at')

class ProduceListingSerializer(serializers.ModelSerializer):
    farmer = UserSerializer(read_only=True)
    farmer_id = serializers.PrimaryKeyRelatedField(write_only=True, queryset=User.objects.filter(role='farmer'), source='farmer')
    class Meta:
        model = ProduceListing
        fields = ('croplisting_id', 'farmer', 'farmer_id', 'crop', 'quantity', 'created_at')
        read_only_fields = ('croplisting_id', 'created_at')

class OrderSerializer(serializers.ModelSerializer):
    croplisting = ProduceListingSerializer(read_only = True)
    class Meta:
        model = Order
        fields = ('order_id', 'cart', 'wholesaler', 'croplisting', 'created_at', 'updated_at')

class CartSerializer(serializers.ModelSerializer):
    orders = OrderSerializer(many = True, read_only = True)
    class Meta:
        model = Cart
        fields = ('cart_id', 'wholesaler', 'created_at', 'updated_at')
        
class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = ('payment_id', 'order', 'amount', 'payment_status', 'transaction_ref', 'created_at')











