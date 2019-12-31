from src.base.models import Employment, Shop
from rest_framework import permissions
from rest_framework.exceptions import ValidationError


class Permission(permissions.BasePermission):
    actions ={
        'list':'GET',
        'create':'POST',
        'retrieve':'GET',
        'update':'PUT',
        'destroy':'DELETE'
    }

    def has_permission(self, request, view):
        # if request.method in permissions.SAFE_METHODS:
        #     return True
        employments = Employment.objects.get_active(
            user=request.user)
        return self.check_employment_permission(employments, request, view)

    def has_object_permission(self, request, view, obj):
        department = obj.get_department()

        employments = Employment.objects.get_active(
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            user=request.user)

        return self.check_employment_permission(employments, request, view)

    def check_employment_permission(self, employments, request, view):
        method = request.method
        action = view.action
        func = view.basename

        request.employments=employments

        if not self.actions.get(action) or method != self.actions[action]:
            func = f"{func}_{action}"
        if method in permissions.SAFE_METHODS:
            # OPTIONS и HEAD еще могут быть
            method = 'GET'
        for employment in employments:
            if employment.has_permission(func, method):
                return True
        return False


class FilteredListPermission(Permission):
    def has_permission(self, request, view):
        if view.action == 'retrieve':
            # Права для объекта проверятся в has_object_permission
            return True

        if request.method == 'GET':
            shop_id = request.query_params.get('shop_id')
        else:
            shop_id = request.data.get('shop_id')
        if not shop_id:
            raise ValidationError("shop_id should be defined")
        department = Shop.objects.get(id=shop_id)

        employments = Employment.objects.get_active(
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            user=request.user)

        return self.check_employment_permission(employments, request, view)
