from django.db.models import ObjectDoesNotExist, Q
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, NotFound

from src.base.models import Employment, Shop, Employee, Network
from src.timetable.models import WorkerDay, WorkerDayPermission, GroupWorkerDayPermission

from src.timetable.worker_day_permissions.checkers import (
    CreateSingleWdPermissionChecker,
    UpdateSingleWdPermissionChecker,
    DeleteSingleWdPermissionChecker,
)

VIEW_FUNC_ACTIONS = {
    'list': 'GET',
    'create': 'POST',
    'retrieve': 'GET',
    'update': 'PUT',
    'destroy': 'DELETE'
}


def get_view_func(request, view):
    """
    Получение идентификатора api "функции"
    """
    view_func = view.basename or type(view).__name__
    if not VIEW_FUNC_ACTIONS.get(view.action) or request.method != VIEW_FUNC_ACTIONS[view.action]:
        view_func = f"{view_func}_{view.action}"
    return view_func


class Permission(permissions.BasePermission):
    """
    Класс для определения прав доступа к методам апи без привязки к магазину
    """
    def has_permission(self, request, view):
        if not bool(request.user and request.user.is_authenticated):
            return False

        employments = Employment.objects.get_active(
            network_id=request.user.network_id,
            employee__user=request.user,
        ).select_related('position__group')
        return self.check_employment_permission(employments, request, view)

    def has_object_permission(self, request, view, obj):
        employments = Employment.objects.get_active(
            network_id=request.user.network_id,
            employee__user=request.user,
        ).select_related('position__group')

        return self.check_employment_permission(employments, request, view)

    def check_employment_permission(self, employments, request, view):
        request.employments = employments
        func = get_view_func(request, view)
        for employment in employments:
            if employment.has_permission(func, request.method):
                return True
        return False


class WdPermission(Permission):
    def _set_is_vacancy(self, wd_data):
        # рефакторинг
        if 'is_vacancy' not in wd_data and wd_data.get('employee_id') and wd_data.get(
                'shop_id') and wd_data.get('dt'):
            wd_data['is_vacancy'] = not Employment.objects.get_active(
                employee_id=wd_data.get('employee_id'),
                shop_id=wd_data.get('shop_id'),
                dt_from=wd_data.get('dt'),
                dt_to=wd_data.get('dt'),
            ).exists()

    def has_permission(self, request, view):
        has_permission = super(WdPermission, self).has_permission(request, view)
        if has_permission is False:
            return has_permission

        view_action = view.action.lower()
        if view_action in ['create', 'update', 'destroy']:  # TODO: approve? -- для подтверждения конкретного рабочего дня
            if view_action == 'create':
                wd_data = request.data
                self._set_is_vacancy(wd_data=wd_data)
                return CreateSingleWdPermissionChecker(user=request.user, wd_data=wd_data).has_permission()
            elif view_action == 'update':
                wd_id = view.kwargs['pk']
                wd_data = WorkerDay.objects.filter(id=wd_id).values(
                    'type', 
                    'dt', 
                    'is_fact', 
                    'employee_id', 
                    'shop_id',
                    'is_vacancy',
                ).first()
                if not wd_data:
                    return NotFound(_('Not found worker day with id={wd_id}').format(wd_id=wd_id))
                if wd_data['type'] != request.data.get('type') or wd_data['shop_id'] != request.data.get('shop_id') or \
                        wd_data['dt'] != request.data.get('dt'):
                    # TODO: опционально или на постоянку такую логику оставить?
                    has_delete_permission = DeleteSingleWdPermissionChecker(
                        user=request.user, wd_id=wd_id).has_permission()
                    if has_delete_permission is False:
                        return False
                    wd_data = request.data
                    self._set_is_vacancy(wd_data=wd_data)
                    has_create_permission = CreateSingleWdPermissionChecker(
                        user=request.user, wd_data=wd_data).has_permission()
                    if has_create_permission is False:
                        return False
                else:
                    return UpdateSingleWdPermissionChecker(
                        user=request.user, wd_id=wd_id, wd_data=wd_data).has_permission()
            elif view_action == 'destroy':
                wd_id = view.kwargs['pk']
                return DeleteSingleWdPermissionChecker(user=request.user, wd_id=wd_id).has_permission()

            # return wd_perm_checker_cls(**wd_perm_checker_kwargs).has_permission()
            # GroupWorkerDayPermission.has_permission(
            #     user=request.user,
            #     action=action,
            #     graph_type=WorkerDayPermission.FACT if wd_data.get('is_fact') else WorkerDayPermission.PLAN,
            #     wd_type=wd_data.get('type'),
            #     wd_dt=wd_data.get('dt'),
            # ) and WorkerDay._has_group_permissions(request.user, wd_data.get('employee_id'), wd_data.get('dt'), is_vacancy=wd_data.get('is_vacancy', False), shop_id=wd_data.get('shop_id'))

        return has_permission


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
            employee__user=request.user,
        )

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
            employment = Employment.objects.select_related('shop', 'employee__user').get(id=employment_id)
        except ObjectDoesNotExist:
            raise NotFound("Employment does not exist")

        department = employment.shop

        employments = Employment.objects.get_active(
            shop__in=department.get_ancestors(include_self=True, ascending=True),
            employee__user=request.user,
            extra_q=Q(
                Q(shop__network_id=employment.shop.network_id)|
                Q(employee__user__network_id=employment.shop.network_id) |
                Q(shop__network_id=employment.employee.user.network_id)|
                Q(employee__user__network_id=employment.employee.user.network_id)
            )
        )

        return self.check_employment_permission(employments, request, view)
