from django.db.models import ObjectDoesNotExist
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, NotFound

from src.base.models import Employment, Shop


class Permission(permissions.BasePermission):
    """
    Класс для определения прав доступа к методам апи без привязки к магазину
    """
    actions ={
        'list': 'GET',
        'create': 'POST',
        'retrieve': 'GET',
        'update': 'PUT',
        'destroy': 'DELETE'
    }

    def has_permission(self, request, view):
        if not bool(request.user and request.user.is_authenticated):
            return False

        employments = Employment.objects.get_active(
            network_id=request.user.network_id,
            user=request.user
        ).select_related('position')
        return self.check_employment_permission(employments, request, view)

    def has_object_permission(self, request, view, obj):
        employments = Employment.objects.get_active(
            network_id=request.user.network_id,
            user=request.user
        ).select_related('position')

        return self.check_employment_permission(employments, request, view)

    def check_employment_permission(self, employments, request, view):
        method = request.method
        action = view.action
        func = view.basename or type(view).__name__

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
    """
    Класс для определения прав доступа к методам апи для конкретного магазина
    """
    def has_permission(self, request, view):
        if not bool(request.user and request.user.is_authenticated):
            return False
        if view.action == 'retrieve':
            # Права для объекта проверятся в has_object_permission
            return True

        if request.method == 'GET':
            shop_id = request.query_params.get('shop_id')
            shop_code = request.query_params.get('shop_code')
            if not shop_id and not shop_code:
                raise ValidationError(_("shop_id should be defined"))
        else:
            shop_id = request.data.get('shop_id')
            # shop_id не меняется, права задаются has_object_permission
            if not shop_id:
                return True
        department = Shop.objects.get(id=shop_id) if shop_id else Shop.objects.get(code=shop_code)

        employments = Employment.objects.get_active(
            network_id=request.user.network_id,
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            user=request.user)

        return self.check_employment_permission(employments, request, view)


class EmploymentFilteredListPermission(Permission):
    """
    Класс для определения прав доступа к методам апи по employment
    """
    def has_permission(self, request, view):
        if not bool(request.user and request.user.is_authenticated):
            return False
        if view.action == 'retrieve':
            # Права для объекта проверятся в has_object_permission
            return True

        employment_id = view.kwargs.get('employment_pk')

        try:
            employment = Employment.objects.get(id=employment_id)
        except ObjectDoesNotExist:
            raise NotFound("Employment does not exist")

        department = employment.shop

        employments = Employment.objects.get_active(
            employment.user.network_id,
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            user=request.user,
        )

        return self.check_employment_permission(employments, request, view)
