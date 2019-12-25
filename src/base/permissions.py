from src.base.models import Employment
from rest_framework import permissions


class Permission(permissions.BasePermission):
    def has_permission(self, request, view):
        if request.method in permissions.SAFE_METHODS:
            return True
        employments = Employment.objects.get_active(
            user=request.user)
        for employment in employments:
            #TODO: права только дочерние магазины создавать?
            if employment.has_permission(view.basename, request.method):
                return True

        return False


    def has_object_permission(self, request, view, obj):
        department = obj.get_department()
        # if request.method in permissions.SAFE_METHODS:
        #     return True

        employments = Employment.objects.get_active(
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            user=request.user)

        method = request.method
        if method in permissions.SAFE_METHODS:
            # OPTIONS и HEAD еще могут быть
            method = 'GET'
        for employment in employments:
            if employment.has_permission(view.basename, method):
                return True
        return False
