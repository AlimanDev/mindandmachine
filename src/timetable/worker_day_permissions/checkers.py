from datetime import datetime, date, timedelta

from django.conf import settings
from django.db.models import Q, F
from django.utils.translation import gettext as _

from django.utils.encoding import force_str
from src.base.models import (
    Employee,
    Shop,
    Group,
    Employment,
    NetworkConnect,
)
from src.timetable.models import (
    WorkerDay,
    WorkerDayType,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from .serializers import WsPermissionDataSerializer
from src.util.models_converter import Converter


class BaseWdPermissionChecker:
    action = None

    def __init__(self, user, cached_data=None, check_active_empl=True,):
        """
        :param user:
        :param cached_data:
            user_shops
            get_subordinated_group_ids
            wd_types_dict
        :param check_active_empl: checks active employment
        """
        self.user = user
        self.cached_data = cached_data or {}
        self.err_message = None
        self.check_active_empl = check_active_empl

    def _get_err_msg(self, action, wd_type_id, employee_id=None, shop_id=None, dt_interval=None):
        # рефакторинг
        from src.timetable.worker_day.views import WorkerDayViewSet
        wd_type_display_str = (self.cached_data.get(
            'wd_types_dict', {}) or WorkerDayType.get_wd_types_dict()).get(wd_type_id).name
        action_str = force_str(WorkerDayPermission.ACTIONS_DICT.get(action)).lower()
        if dt_interval:
            err_msg = WorkerDayViewSet.error_messages['wd_interval_restriction'].format(
                wd_type_str=wd_type_display_str,
                action_str=action_str,
                dt_interval=dt_interval,
            )
        else:
            err_msg = WorkerDayViewSet.error_messages['no_action_perm_for_wd_type'].format(
                wd_type_str=wd_type_display_str,
                action_str=action_str,
            )
            for_employee_text = force_str(_('for employee'))
            in_department_text = force_str(_('in department'))
            if employee_id:
                err_msg += f" {for_employee_text} {Employee.objects.select_related('user').get(id=employee_id).user.short_fio}"
            if shop_id:
                err_msg += f" {in_department_text} {Shop.objects.filter(id=shop_id).values_list('name', flat=True).first()}"

        return err_msg

    def has_group_permission(self, employee_id, shop_id, action, graph_type, wd_type_id, dt_from, dt_to, is_vacancy):
        if isinstance(dt_from, str):
            dt_from = datetime.strptime(dt_from, settings.QOS_DATE_FORMAT).date()
        if isinstance(dt_to, str):
            dt_to = datetime.strptime(dt_to, settings.QOS_DATE_FORMAT).date()

        if employee_id and self.check_active_empl:
            active_empls = Employment.objects.get_active(
                dt_from=dt_from,
                dt_to=dt_to,
                employee_id=employee_id,
            )
            if not active_empls.exists():
                self.err_message = _("You are not employed during this period")
                return False

        self.user_shops = self.cached_data.get('user_shops') or self.user.get_shops(
            include_descendants=True).values_list('id', flat=True)
        self.user_subordinated_group_ids = self.cached_data.get(
            'user_subordinated_group_ids') or Group.get_subordinated_group_ids(self.user)

        self.group_wd_permissions = GroupWorkerDayPermission.get_perms_qs(
            user=self.user,
            action=action,
            graph_type=graph_type,
            wd_type_id=wd_type_id,
            is_vacancy=is_vacancy,
        ).order_by(
            F('limit_days_in_past').desc(nulls_first=True),
            F('limit_days_in_future').desc(nulls_first=True),
        ).distinct()
        if not self.group_wd_permissions:
            self.err_message = self._get_err_msg(action, wd_type_id)
            return False

        gwdp: GroupWorkerDayPermission
        for gwdp in self.group_wd_permissions:
            employment_q = self._get_employment_q(gwdp, employee_id, dt_from, dt_to)
            shop_q = self._get_shop_q(gwdp, shop_id)
            if (employment_q or not employee_id) and (shop_q or not shop_id):
                has_perm = (not employee_id or Employment.objects.get_active(
                    dt_from=dt_from,
                    dt_to=dt_to,
                    employee_id=employee_id,
                    extra_q=employment_q,
                ).exists()) and (not shop_id or Shop.objects.filter(
                    shop_q,
                    id=shop_id,
                ).exists())

                if has_perm:
                    return self._check_time_limit(action, gwdp, wd_type_id, shop_id, dt_from, dt_to)

        self.err_message = self._get_err_msg(action, wd_type_id, employee_id=employee_id, shop_id=shop_id)
        return False

    def has_permission(self):
        raise NotImplementedError

    def _get_employment_q(self, gwdp: GroupWorkerDayPermission, employee_id: int, dt_from: date, dt_to: date) -> Q:
        """Lookup for employee_type"""
        if not employee_id:
            employment_q = Q()
        elif gwdp.employee_type == GroupWorkerDayPermission.SUBORDINATE_EMPLOYEE:
            employment_q = Q(
                employee_id__in=self.user.get_subordinates(
                    dt=dt_from,
                    dt_to_shift=dt_to - dt_from,
                    user_shops=self.user_shops,
                    user_subordinated_group_ids=self.user_subordinated_group_ids,
                )
            )
        elif gwdp.employee_type == GroupWorkerDayPermission.MY_SHOPS_ANY_EMPLOYEE:
            employment_q = Q(
                shop_id__in=self.user_shops,
            )
        elif gwdp.employee_type == GroupWorkerDayPermission.MY_NETWORK_EMPLOYEE:
            employment_q = Q(
                employee__user__network_id=self.user.network_id,
                shop__network_id=self.user.network_id,
            )
        elif gwdp.employee_type == GroupWorkerDayPermission.OUTSOURCE_NETWORK_EMPLOYEE:
            employment_q = Q(
                employee__user__network_id__in=NetworkConnect.objects.filter(
                    client_id=self.user.network_id).values_list('outsourcing_id', flat=True),
            )
        else:
            employment_q = Q()

        return employment_q

    def _get_shop_q(self, gwdp: GroupWorkerDayPermission, shop_id: int) -> Q:
        """Lookup for shop_type"""
        if not shop_id:
            shop_q = Q()
        elif gwdp.shop_type == GroupWorkerDayPermission.MY_SHOPS:
            shop_q = Q(
                id__in=self.user_shops,
            )
        elif gwdp.shop_type == GroupWorkerDayPermission.MY_NETWORK_SHOPS:
            shop_q = Q(
                network_id=self.user.network_id,
            )
        elif gwdp.shop_type == GroupWorkerDayPermission.OUTSOURCE_NETWORK_SHOPS:
            shop_q = Q(
                network_id__in=NetworkConnect.objects.filter(
                    client_id=self.user.network_id).values_list('outsourcing_id', flat=True),
            )
        elif gwdp.shop_type == GroupWorkerDayPermission.CLIENT_NETWORK_SHOPS:
            shop_q = Q(
                network_id__in=NetworkConnect.objects.filter(
                    outsourcing_id=self.user.network_id).values_list('client_id', flat=True),
            )
        else:
            shop_q = Q()

        return shop_q

    def _check_time_limit(
        self,
        action: str,
        gwdp: GroupWorkerDayPermission,
        wd_type_id: int,
        shop_id: int,
        dt_from: date,
        dt_to: date
        ) -> bool :
        """Check time limit"""
        today = (datetime.now() + timedelta(
            hours=Shop.get_cached_tz_offset_by_shop_id(shop_id=shop_id) if shop_id else settings.CLIENT_TIMEZONE)).date()
        date_limit_in_past = None
        date_limit_in_future = None
        if gwdp.limit_days_in_past is not None:
            date_limit_in_past = today - timedelta(days=gwdp.limit_days_in_past)
        if gwdp.limit_days_in_future is not None:
            date_limit_in_future = today + timedelta(days=gwdp.limit_days_in_future)
        if date_limit_in_past or date_limit_in_future:
            if (date_limit_in_past and dt_from < date_limit_in_past) or \
                    (date_limit_in_future and dt_to > date_limit_in_future):
                dt_interval = f'с {Converter.convert_date(date_limit_in_past) or "..."} ' \
                                f'по {Converter.convert_date(date_limit_in_future) or "..."}'
                self.err_message = self._get_err_msg(action, wd_type_id, dt_interval=dt_interval)
                return False
        return True


class BaseSingleWdPermissionChecker(BaseWdPermissionChecker):
    def _has_single_permission(self, employee_id, shop_id, action, graph_type, wd_type_id, wd_dt, is_vacancy):
        return self.has_group_permission(employee_id, shop_id, action, graph_type, wd_type_id, dt_from=wd_dt, dt_to=wd_dt, is_vacancy=is_vacancy)


class BaseSingleWdDataPermissionChecker(BaseSingleWdPermissionChecker):
    def __init__(self, *args, wd_data, **kwargs):
        """
        :param wd_data:
            dt
            wd_type_id
            employee_id
            shop_id
            is_vacancy
        """
        self.wd_data = wd_data
        super(BaseSingleWdDataPermissionChecker, self).__init__(*args, **kwargs)

    def _has_single_wd_data_permission(self):
        # рефакторинг
        wd_type_id = self.wd_data.get('type_id') or self.wd_data.get('type')
        if isinstance(wd_type_id, WorkerDayType):
            wd_type_id = wd_type_id.code

        return self._has_single_permission(
            employee_id=self.wd_data.get('employee_id'),
            shop_id=self.wd_data.get('shop_id'),
            action=self.action,
            graph_type=WorkerDayPermission.FACT if self.wd_data.get('is_fact') else WorkerDayPermission.PLAN,
            wd_type_id=wd_type_id,
            wd_dt=self.wd_data.get('dt'),
            is_vacancy=self.wd_data.get('is_vacancy'),
        )


# class BaseListWdPermissionChecker(BaseWdPermissionChecker):
#     def __init__(self, *args, wd_list, **kwargs):
#         """
#         :param wd_list:
#             dt
#             type_id
#             employee_id
#             shop_id
#             is_vacancy
#         """
#         self.wd_list = wd_list
#         super(BaseListWdPermissionChecker, self).__init__(*args, **kwargs)


class CreateSingleWdPermissionChecker(BaseSingleWdDataPermissionChecker):
    action = WorkerDayPermission.CREATE

    def __init__(self, *args, need_preliminary_wd_data_check=False, **kwargs):
        """
        :param need_preliminary_wd_data_check: нужна предвариельная проверка данных
        """
        self.need_preliminary_wd_data_check = need_preliminary_wd_data_check
        super(CreateSingleWdPermissionChecker, self).__init__(*args, **kwargs)

    def _preliminary_wd_data_check(self):
        # проверка django-пермишнов происходит раньше, чем валидация данных,
        # поэтому предварительно провалидируем данные, используемые для проверки доступа
        WsPermissionDataSerializer(data=self.wd_data).is_valid(raise_exception=True)

    def has_permission(self):
        if self.need_preliminary_wd_data_check:
            self._preliminary_wd_data_check()

        return self._has_single_wd_data_permission()


class UpdateSingleWdPermissionChecker(BaseSingleWdDataPermissionChecker):
    action = WorkerDayPermission.UPDATE

    def has_permission(self):
        return self._has_single_wd_data_permission()


class DeleteSingleWdDataPermissionChecker(BaseSingleWdDataPermissionChecker):
    action = WorkerDayPermission.DELETE

    def has_permission(self):
        return self._has_single_wd_data_permission()


class DeleteSingleWdPermissionChecker(BaseSingleWdPermissionChecker):
    action = WorkerDayPermission.DELETE

    def __init__(self, *args, wd_obj=None, wd_id=None, **kwargs):
        assert wd_obj or wd_id
        self.wd_obj = wd_obj
        self.wd_id = wd_id
        super(DeleteSingleWdPermissionChecker, self).__init__(*args, **kwargs)

    def has_permission(self):
        if not self.wd_obj:
            self.wd_obj = WorkerDay.objects.filter(id=self.wd_id).first()

        if not self.wd_obj:
            return True

        return self._has_single_permission(
            employee_id=self.wd_obj.employee_id,
            shop_id=self.wd_obj.shop_id,
            action=self.action,
            graph_type=WorkerDayPermission.FACT if self.wd_obj.is_fact else WorkerDayPermission.PLAN,
            wd_type_id=self.wd_obj.type_id,
            wd_dt=self.wd_obj.dt,
            is_vacancy=self.wd_obj.is_vacancy,
        )


class BaseQsWdPermissionChecker(BaseWdPermissionChecker):
    pass


class DeleteQsWdPermissionChecker(BaseQsWdPermissionChecker):
    action = WorkerDayPermission.DELETE

    def __init__(self, *args, wd_qs, **kwargs):
        self.wd_qs = wd_qs
        super(DeleteQsWdPermissionChecker, self).__init__(*args, **kwargs)

    def has_permission(self):
        for wd in self.wd_qs:
            if not DeleteSingleWdPermissionChecker(
                    user=self.user, wd_obj=wd, cached_data=self.cached_data).has_permission():
                self.err_message = self._get_err_msg(
                    self.action, wd.type_id, employee_id=wd.employee_id, shop_id=wd.shop_id)
                return False

        return True


# class UpdateQsWdPermissionChecker(BaseQsWdPermissionChecker):
#     pass  # TODO: используется?


class ApproveQsWdPermissionChecker(BaseQsWdPermissionChecker):
    action = WorkerDayPermission.APPROVE

    def __init__(self, *args, wd_qs, **kwargs):
        self.wd_qs = wd_qs
        super(ApproveQsWdPermissionChecker, self).__init__(*args, **kwargs)
