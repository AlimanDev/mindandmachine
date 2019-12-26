from src.base.models import Employment
from rest_framework import permissions


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
        if not self.actions.get(action) or method != self.actions[action]:
            func = f"{func}_{action}"
        if method in permissions.SAFE_METHODS:
            # OPTIONS и HEAD еще могут быть
            method = 'GET'
        for employment in employments:
            if employment.has_permission(func, method):
                return True
        return False
