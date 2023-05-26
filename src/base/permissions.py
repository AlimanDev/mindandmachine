from django.db.models import ObjectDoesNotExist, Q
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, NotFound
from src.base.models import Employment, Shop
from src.timetable.models import WorkerDay
from src.timetable.worker_day.serializers import WorkerDaySerializer
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
        if 'is_vacancy' not in wd_data:
            plan = WorkerDay.objects.filter(is_fact=False, is_approved=True, employee_id=wd_data.get('employee_id'),
                                            dt=wd_data.get('dt')).first()
            if plan and wd_data.get('is_fact'):
                wd_data['is_vacancy'] = plan.is_vacancy
            elif wd_data.get('employee_id') and wd_data.get('shop_id') and wd_data.get('dt'):
                wd_data['is_vacancy'] = not Employment.objects.get_active(
                    employee_id=wd_data.get('employee_id'),
                    shop_id=wd_data.get('shop_id'),
                    dt_from=wd_data.get('dt'),
                    dt_to=wd_data.get('dt'),
                ).exists()

    def _has_perm(self, perm_checker):
        has_perm = perm_checker.has_permission()
        if has_perm is False:
            self.message = perm_checker.err_message
        return has_perm

    def has_permission(self, request, view):
        has_permission = super(WdPermission, self).has_permission(request, view)
        if has_permission is False:
            return has_permission

        view_action = view.action.lower()
        if view_action in ['create', 'update', 'destroy']:
            if view_action == 'create':
                wd_data = request.data
                self._set_is_vacancy(wd_data=wd_data)
                perm_checker = CreateSingleWdPermissionChecker(
                    user=request.user, wd_data=wd_data, need_preliminary_wd_data_check=True)
                return self._has_perm(perm_checker)
            elif view_action == 'update':
                wd_id = view.kwargs['pk']
                wd_instance: WorkerDay = WorkerDay.objects.filter(id=wd_id).first()
                if not wd_instance:
                    return NotFound(_('Not found worker day with id={wd_id}').format(wd_id=wd_id))
                wd_data = WorkerDaySerializer(wd_instance).data

                # TODO: опционально или на постоянку такую логику оставить?
                if wd_data['type'] != request.data.get('type') or (wd_instance.shop and wd_data.get('shop_id') != request.data.get('shop_id'))\
                        or wd_data['dt'] != request.data.get('dt'):
                    if request.user.network.settings_values_prop.get('check_delete_single_wd_perm_on_update', True):
                        perm_checker = DeleteSingleWdPermissionChecker(user=request.user, wd_id=wd_id)
                        has_delete_permission = self._has_perm(perm_checker)
                        if has_delete_permission is False:
                            return has_delete_permission
                    wd_data = request.data
                    self._set_is_vacancy(wd_data=wd_data)
                    perm_checker = CreateSingleWdPermissionChecker(
                        user=request.user, wd_data=wd_data, need_preliminary_wd_data_check=True)
                    has_create_permission = self._has_perm(perm_checker)
                    if has_create_permission is False:
                        return False
                else:
                    perm_checker = UpdateSingleWdPermissionChecker(user=request.user, wd_data=wd_data,
                                                                   wd_instance=wd_instance)

                return self._has_perm(perm_checker)
            elif view_action == 'destroy':
                wd_id = view.kwargs['pk']
                perm_checker = DeleteSingleWdPermissionChecker(
                    user=request.user, wd_id=wd_id)
                return self._has_perm(perm_checker)
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
