from datetime import datetime, date, timedelta
from typing import Union

from django.conf import settings
from django.db.models import Q, F
from django.utils.translation import gettext as _

from django.utils.encoding import force_str
from rest_framework.exceptions import PermissionDenied

from src.base.models import (
    Shop,
    Group,
    Employment,
    NetworkConnect,
    User
)
from src.timetable.models import (
    WorkerDay,
    WorkerDayType,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from .serializers import WsPermissionDataSerializer
from src.util.models_converter import Converter
from ..worker_day.utils.utils import can_edit_worker_day
from src.util.decorators import cached_method


class BaseWdPermissionChecker:
    action = None

    def __init__(
        self,
        user: User,
        cached_data: dict = None,
        check_active_empl=True,
        shop_id: int = None,
        shop: Shop = None
        ):
        """
        :param cached_data:
            _user_shops_ids
            _user_subordinated_group_ids
            _user_subordinates_ids
            wd_types_dict
        """
        self.user = user
        self.cached_data = cached_data or {}
        self.err_message = None
        self.check_active_empl = check_active_empl
        if shop_id:
            self.shop = Shop.objects.get(id=shop_id)
        elif shop:
            self.shop = shop
        else:
            self.shop = None

    def has_group_permission(
        self,
        action: str,
        graph_type: str,
        wd_type_id: int,
        dt_from: Union[date, str],
        dt_to: Union[date, str],
        is_vacancy: bool,
        employee_id: Union[int, None] = None,
        employment: Union[int, None] = None,
    ):
        if isinstance(dt_from, str):
            dt_from = datetime.strptime(dt_from, settings.QOS_DATE_FORMAT).date()
        if isinstance(dt_to, str):
            dt_to = datetime.strptime(dt_to, settings.QOS_DATE_FORMAT).date()

        if employee_id and not employment:
            employment = Employment.objects.get_active(
                dt_from=dt_from,
                dt_to=dt_to,
                employee_id=employee_id,
            ).select_related(
                'employee', 'employee__user'
            ).first()
        if self.check_active_empl and employee_id and not employment:
            # `employee_id` passed and no active `employment` found. 
            # If `employment` is passed instead - it is assumed to be active. Validate beforehand.
            self.err_message = _("Can't create a working day in the schedule, since the user is not employed during this period")
            return False

        self.group_wd_permissions = self._get_group_wd_permissions(action, graph_type, wd_type_id, is_vacancy)
        if not self.group_wd_permissions:
            self.err_message = self._get_err_msg(action, wd_type_id)
            return False

        gwdp: GroupWorkerDayPermission
        for gwdp in self.group_wd_permissions:
            has_perm = (not employment or self._check_employment_perm(gwdp, employment, dt_from, dt_to)) \
                and (not self.shop or self._check_shop_perm(gwdp))

            if has_perm:
                return self._check_time_limit(action, gwdp, wd_type_id, dt_from, dt_to)
        self.err_message = self._get_err_msg(action, wd_type_id, employee=employment.employee if employment else None)
        return False

    def has_permission(self):
        raise NotImplementedError

    def _check_employment_perm(self, gwdp: GroupWorkerDayPermission, employment: Employment, dt_from: date, dt_to: date) -> Q:
        """Check for employee_type"""
        if gwdp.employee_type == GroupWorkerDayPermission.SUBORDINATE_EMPLOYEE:
            return employment.employee.id in self._user_subordinates_ids(dt_from, dt_to)
        elif gwdp.employee_type == GroupWorkerDayPermission.MY_SHOPS_ANY_EMPLOYEE:
            return employment.shop_id in self._user_shops_ids
        elif gwdp.employee_type == GroupWorkerDayPermission.MY_NETWORK_EMPLOYEE:
            return employment.employee.user.network_id == self.user.network_id \
                and employment.shop.network_id == self.user.network_id
        elif gwdp.employee_type == GroupWorkerDayPermission.OUTSOURCE_NETWORK_EMPLOYEE:
            return employment.employee.user.network_id in NetworkConnect.objects.filter(
                client_id=self.user.network_id
            ).values_list('outsourcing_id', flat=True)
        else:
            raise ValueError(f'Unknown GroupWorkerDayPermission.employee_type {gwdp.employee_type}')

    def _check_shop_perm(self, gwdp: GroupWorkerDayPermission) -> bool:
        """Check for shop_type"""
        if gwdp.shop_type == GroupWorkerDayPermission.MY_SHOPS:
            return self.shop.id in self._user_shops_ids
        elif gwdp.shop_type == GroupWorkerDayPermission.MY_NETWORK_SHOPS:
            return self.shop.network_id == self.user.network_id
        elif gwdp.shop_type == GroupWorkerDayPermission.OUTSOURCE_NETWORK_SHOPS:
            return self.shop.network_id in NetworkConnect.objects.filter(
                client_id=self.user.network_id
            ).values_list('outsourcing_id', flat=True),
        elif gwdp.shop_type == GroupWorkerDayPermission.CLIENT_NETWORK_SHOPS:
            return self.shop.network_id in NetworkConnect.objects.filter(
                outsourcing_id=self.user.network_id
            ).values_list('client_id', flat=True)
        else:
            raise ValueError(f'Unknown GroupWorkerDayPermission.shop_type {gwdp.shop_type}')

    def _check_time_limit(
        self,
        action: str,
        gwdp: GroupWorkerDayPermission,
        wd_type_id: int,
        dt_from: date,
        dt_to: date
    ) -> bool :
        """Check time limit"""
        today = (datetime.now() + timedelta(
            hours=self.shop.get_tz_offset() if self.shop else settings.CLIENT_TIMEZONE)).date()
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

    @cached_method
    def _get_group_wd_permissions(
        self,
        action: str,
        graph_type: str,
        wd_type_id: int,
        is_vacancy: bool
    ):
        """Cached group wd premissions (by arguments)."""
        # TODO: Possible further refactoring for approving: pass a pre-requested list for all wd_types and filter in memory)
        return GroupWorkerDayPermission.get_perms_qs(
            user=self.user,
            action=action,
            graph_type=graph_type,
            wd_type_id=wd_type_id,
            is_vacancy=is_vacancy,
        ).order_by(
            F('limit_days_in_past').desc(nulls_first=True),
            F('limit_days_in_future').desc(nulls_first=True),
        ).distinct()

    @property
    @cached_method
    def _wd_types_dict(self):
        return WorkerDayType.get_wd_types_dict()

    @property
    @cached_method
    def _user_shops_ids(self) -> tuple[int]:
        return tuple(
            self.user.get_shops(
                include_descendants=True
            ).values_list('id', flat=True)
        )

    @property
    @cached_method
    def _user_subordinated_group_ids(self) -> tuple[int]:
        return tuple(Group.get_subordinated_group_ids(self.user))

    @cached_method
    def _user_subordinates_ids(self, dt_from: date, dt_to: date) -> tuple[int]:
        """Cached subordinates (by `dt_to` and `dt_from` pairs)"""
        return tuple(self.user.get_subordinates(
            dt=dt_from,
            dt_to_shift=dt_to - dt_from,
            user_shops=self._user_shops_ids,
            user_subordinated_group_ids=self._user_subordinated_group_ids,   
        ).values_list('id', flat=True))

    def _get_err_msg(self, action, wd_type_id, employee=None, dt_interval=None):
        # рефакторинг
        from src.timetable.worker_day.views import WorkerDayViewSet
        wd_type_display_str = self._wd_types_dict.get(wd_type_id).name
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
            if employee:
                err_msg += f" {for_employee_text} {employee.user.short_fio}"
            if self.shop:
                err_msg += f" {in_department_text} {self.shop.name}"

        return err_msg


class BaseSingleWdPermissionChecker(BaseWdPermissionChecker):
    def _has_single_permission(self, employee_id, action, graph_type, wd_type_id, wd_dt, is_vacancy):
        return self.has_group_permission(
            employee_id=employee_id,
            action=action,
            graph_type=graph_type,
            wd_type_id=wd_type_id,
            dt_from=wd_dt,
            dt_to=wd_dt,
            is_vacancy=is_vacancy,
        )


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
        super(BaseSingleWdDataPermissionChecker, self).__init__(*args, **kwargs, shop_id=wd_data.get('shop_id'))

    def _has_single_wd_data_permission(self):
        # рефакторинг
        wd_type_id = self.wd_data.get('type_id') or self.wd_data.get('type')
        if isinstance(wd_type_id, WorkerDayType):
            wd_type_id = wd_type_id.code

        return self._has_single_permission(
            employee_id=self.wd_data.get('employee_id'),
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

    def __init__(self, *args, wd_instance=None, **kwargs):
        self.wd_instance = wd_instance
        super(UpdateSingleWdPermissionChecker, self).__init__(*args, **kwargs)

    def has_permission(self):
        if not self.wd_instance:
            return True
        if not can_edit_worker_day(self.wd_instance, self.user):
            raise PermissionDenied(_('You do not have rights to change protected worker days.'))
        return self._has_single_wd_data_permission()


class DeleteSingleWdDataPermissionChecker(BaseSingleWdDataPermissionChecker):
    action = WorkerDayPermission.DELETE

    def __init__(self, *args, wd_instance=None, **kwargs):
        self.wd_instance = wd_instance
        super(DeleteSingleWdDataPermissionChecker, self).__init__(*args, **kwargs)

    def has_permission(self):
        if not self.wd_instance:
            return True
        if not can_edit_worker_day(self.wd_instance, self.user):
            raise PermissionDenied(_('You do not have rights to change protected worker days.'))
        return self._has_single_wd_data_permission()


class DeleteSingleWdPermissionChecker(BaseSingleWdPermissionChecker):
    action = WorkerDayPermission.DELETE

    def __init__(self, *args, wd_obj=None, wd_id=None   , **kwargs):
        assert wd_obj or wd_id
        if wd_obj:
            self.wd_obj = wd_obj
        else:
            self.wd_obj = WorkerDay.objects.filter(id=wd_id).select_related('shop').first()
        shop = wd_obj.shop if wd_obj else None
        super(DeleteSingleWdPermissionChecker, self).__init__(*args, shop=shop,  **kwargs)

    def has_permission(self):
        if not self.wd_obj:
            return True
        if not can_edit_worker_day(self.wd_obj, self.user):
            raise PermissionDenied(_('You do not have rights to change protected worker days.'))

        return self._has_single_permission(
            employee_id=self.wd_obj.employee_id,
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
            sub_checker = DeleteSingleWdPermissionChecker(
                user=self.user, wd_obj=wd, cached_data=self.cached_data
            )
            if not sub_checker.has_permission():
                self.err_message = sub_checker.err_message
                return False

        return True


# class UpdateQsWdPermissionChecker(BaseQsWdPermissionChecker):
#     pass  # TODO: используется?


class ApproveQsWdPermissionChecker(BaseQsWdPermissionChecker):
    action = WorkerDayPermission.APPROVE

    def __init__(self, *args, wd_qs, **kwargs):
        self.wd_qs = wd_qs
        super(ApproveQsWdPermissionChecker, self).__init__(*args, **kwargs)
