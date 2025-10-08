from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

ROLE_CHOICES = (
    ('farmer', 'Farmer'),
    ('wholesaler', 'Wholesaler'),
    ('admin', 'Admin'),
)
ORDER_STATUS_CHOICES = [
    ('unpaid', 'Unpaid'),
    ('paid', 'Paid')
]
PAYMENT_STATUS_CHOICES = (
    ('completed', 'Completed'),
    ('failed', 'Failed'),
)
SMS_STATUS_CHOICES = (
    ('delivered', 'Delivered'),
    ('failed', 'Failed'),
)

def normalize_phone(phone):
    if not phone:
        return ""
    return phone.replace('+', '').replace(' ', '').lstrip('0')

class User(models.Model):
    user_id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=50)
    role = models.CharField(max_length=50, choices=ROLE_CHOICES)
    location = models.CharField(max_length=50, null=True, blank=True)
    phone_number = models.CharField(max_length=15, unique=True, null=False, blank=False, default="0000000000")
    created_at = models.DateTimeField(auto_now_add=True)
    def save(self, *args, **kwargs):
        self.phone_number = normalize_phone(self.phone_number)
        super().save(*args, **kwargs)
    def __str__(self):
        return f"{self.name} ({self.phone_number})"

class Crop(models.Model):
    crop_id = models.AutoField(primary_key=True)
    crop_name = models.CharField(max_length=50, unique=True)
    def __str__(self):
        return self.crop_name

class ProduceListing(models.Model):
    croplisting_id = models.AutoField(primary_key=True)
    farmer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='produce_listings')
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"{self.quantity} of {self.crop.crop_name} by {self.farmer.name}"

class Cart(models.Model):
    cart_id = models.AutoField(primary_key=True)
    wholesaler = models.OneToOneField(User, on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"Cart for {self.wholesaler.name}"

class Order(models.Model):
    order_id = models.AutoField(primary_key=True)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='orders')
    wholesaler = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    croplisting = models.OneToOneField(ProduceListing, on_delete=models.CASCADE)
    price = models.DecimalField(max_digits=12, decimal_places=2, null=False, blank=False)
    status = models.CharField(max_length=10, choices=ORDER_STATUS_CHOICES, default='unpaid')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"Order {self.order_id} by {self.wholesaler.name}"

class Payment(models.Model):
    payment_id = models.AutoField(primary_key=True)
    order = models.OneToOneField(Order, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES)
    transaction_ref = models.CharField(max_length=50, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"Payment {self.payment_id} for Order {self.order.order_id}"

class MarketPrice(models.Model):
    market_price_id = models.AutoField(primary_key=True)
    crop = models.ForeignKey(Crop, on_delete=models.CASCADE)
    location = models.CharField(max_length=20)
    price_per_unit = models.DecimalField(max_digits=10, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    def __str__(self):
        return f"{self.crop.crop_name} price in {self.location}"

class SMSLogs(models.Model):
    smslog_id = models.AutoField(primary_key=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sms_logs')
    message_body = models.TextField()
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=SMS_STATUS_CHOICES)
    def __str__(self):
        return f"SMS to {self.user.name} at {self.sent_at}"

class USSDSession(models.Model):
    session_id = models.CharField(max_length=100, unique=True)
    phone_number = models.CharField(max_length=15)
    data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    def __str__(self):
        return f"USSD Session {self.session_id} for {self.phone_number}"

@receiver(post_save, sender=User)
def create_wholesaler_cart(sender, instance, created, **kwargs):
    if created and instance.role == 'wholesaler':
        Cart.objects.get_or_create(wholesaler=instance)