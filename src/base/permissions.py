from src.base.models import Employment, Shop
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, NotFound
from django.db.models import ObjectDoesNotExist, Q

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
            user=request.user)
        return self.check_employment_permission(employments, request, view)

    def has_object_permission(self, request, view, obj):
        department = obj.get_department()

        # q = Q()
        # if department:
        #     q=Q(shop__in=department.get_ancestors(include_self=True, ascending=True))

        employments = Employment.objects.get_active(
            user=request.user)#.filter(q)

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
            if not shop_id:
                raise ValidationError("shop_id should be defined")
        else:
            shop_id = request.data.get('shop_id')
            # shop_id не меняется, права задаются has_object_permission
            if not shop_id:
                return True
        department = Shop.objects.get(id=shop_id)

        employments = Employment.objects.get_active(
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

        if request.method == 'GET':
            employment_id = request.query_params.get('employment_id')
            if not employment_id:
                raise ValidationError("employment_id should be defined")
        else:
            if isinstance(request.data, list):
                employment_id = request.data[0].get('employment_id')
                for item in request.data:
                    if item['employment_id'] != employment_id:
                        raise ValidationError("employment_id must be same for all constraints")
            else:
                employment_id = request.data.get('employment_id')
            # shop_id не меняется, права задаются has_object_permission
            if not employment_id:
                return True

        try:
            employment = Employment.objects.get(id=employment_id)
        except ObjectDoesNotExist:
            raise NotFound( "Employment does not exist")

        department = employment.shop

        employments = Employment.objects.get_active(
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            user=request.user)

        return self.check_employment_permission(employments, request, view)
