from rest_framework import permissions
from django.conf import settings
class IsFarmer(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, 'role', None) == 'farmer')
    
class IsWholesaler(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, 'role', None) == 'wholesaler')
    
class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        owner = getattr(obj, 'farmer', None) or getattr(obj, 'wholesaler', None) or getattr(obj, 'user', None)
        return owner == request.user
    
class FarmerListingPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(request.user, 'role', None) == 'farmer'
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        return obj.farmer == request.user
    
class WholesalerCartPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, 'role', None) == 'wholesaler')
    def has_object_permission(self, request, view, obj):
        if getattr(request.user, 'role', None) != 'wholesaler':
            return False
        if request.method in permissions.SAFE_METHODS:
            return obj.wholesaler == request.user
        if request.method in ['PUT', 'PATCH']:
            return obj.wholesaler == request.user
        if request.method == 'DELETE':
            return False
        return obj.wholesaler == request.user
    
class OrderPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(request.user, 'role', None) == 'wholesaler'
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.croplisting.farmer == request.user or obj.wholesaler == request.user
        return obj.wholesaler == request.user
    
class PaymentPermission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        return getattr(request.user, 'role', None) == 'wholesaler'
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return obj.order.croplisting.farmer == request.user or obj.order.wholesaler == request.user
        return obj.order.wholesaler == request.user
    
class IsProjectAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        user = getattr(request, 'user', None)
        if not user:
            return False
        if getattr(user, 'role', None) == 'admin':
            return True
        allowed = getattr(settings, 'ALLOWED_ADMIN_IDENTIFIERS', [])
        phone = getattr(user, 'phone_number', None)
        email = getattr(user, 'email', None)
        if phone and phone in allowed:
            return True
        if email and email in allowed:
            return True
        return False











