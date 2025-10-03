from django.contrib import admin
from .models import User, Crop, MarketPrice, ProduceListing, Cart, Order, Payment, SMSLogs, USSDSession

class ReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False
    def has_delete_permission(self, request, obj=None):
        return False
    def has_change_permission(self, request, obj=None):
        return False
    def get_actions(self, request):
        actions = super().get_actions(request)
        if "delete_selected" in actions:
            del actions["delete_selected"]
        return actions

admin.site.register(Crop)
admin.site.register(MarketPrice)
admin.site.register(ProduceListing, ReadOnlyAdmin)
admin.site.register(Order, ReadOnlyAdmin)
admin.site.register(Payment, ReadOnlyAdmin)
admin.site.register(SMSLogs, ReadOnlyAdmin)
admin.site.register(USSDSession, ReadOnlyAdmin) 

@admin.register(User)
class UserAdmin(ReadOnlyAdmin):
    list_display = ('user_id', 'name', 'phone_number', 'role', 'location', 'created_at')
    search_fields = ('name', 'phone_number')
    list_filter = ('role', 'location', 'created_at')

class OrderInline(admin.TabularInline):
    model = Order
    extra = 0
    show_change_link = True

class CartAdmin(ReadOnlyAdmin):
    list_display = ('cart_id', 'wholesaler', 'created_at', 'updated_at')
    inlines = [OrderInline]

admin.site.register(Cart, CartAdmin)

class OrderAdmin(ReadOnlyAdmin):
    list_display = ('order_id', 'cart', 'wholesaler', 'get_crop', 'status', 'created_at')
    def get_crop(self, obj):
        return obj.croplisting.crop.crop_name
    get_crop.short_description = 'Crop'