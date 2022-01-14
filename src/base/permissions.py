from django.db.models import ObjectDoesNotExist, Q
from django.utils.translation import gettext_lazy as _
from rest_framework import permissions
from rest_framework.exceptions import ValidationError, NotFound

from src.base.models import Employment, Shop
from src.timetable.models import WorkerDay, WorkerDayPermission, GroupWorkerDayPermission
from src.timetable.worker_day_permissions.serializers import WsPermissionDataSerializer


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
        if view_action in ['create', 'update', 'destroy']:
            action = WorkerDayPermission.DELETE if view_action == 'destroy' else WorkerDayPermission.CREATE_OR_UPDATE
            if view_action == 'create':
                action_for_group_perm_check = WorkerDayPermission.CREATE
                # проверка пермишнов происходит раньше, чем валидация данных,
                # поэтому предварительно провалидируем данные, используемые для проверки доступа
                WsPermissionDataSerializer(data=request.data).is_valid(raise_exception=True)
                wd_dict = request.data
                self._set_is_vacancy(wd_data=wd_dict)
            else:
                action_for_group_perm_check = WorkerDayPermission.DELETE
                wd_dict = WorkerDay.objects.filter(id=view.kwargs['pk']).values(
                    'type', 
                    'dt', 
                    'is_fact', 
                    'employee_id', 
                    'shop_id',
                    'is_vacancy',
                ).first()
            if not wd_dict:
                return False
            if view_action == 'update':
                action_for_group_perm_check = WorkerDayPermission.UPDATE
                wd_dict['type'] = request.data.get('type', wd_dict.get('type'))
            graph_type = WorkerDayPermission.FACT if wd_dict.get('is_fact') else WorkerDayPermission.PLAN
            return GroupWorkerDayPermission.has_permission(
                user=request.user,
                action=action,
                graph_type=graph_type,
                wd_type=wd_dict.get('type'),
                wd_dt=wd_dict.get('dt'),
            ) and WorkerDay._has_group_permissions(request.user, wd_dict.get('employee_id'), wd_dict.get('dt'),
                                                   is_vacancy=wd_dict.get('is_vacancy', False),
                                                   shop_id=wd_dict.get('shop_id'), action=action_for_group_perm_check,
                                                   graph_type=graph_type)


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
