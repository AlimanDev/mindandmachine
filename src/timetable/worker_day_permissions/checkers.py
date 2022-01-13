from src.timetable.models import (
    WorkerDay,
    WorkerDayPermission,
    GroupWorkerDayPermission,
)
from .serializers import WsPermissionDataSerializer


class BaseWdPermissionChecker:
    action = None

    def __init__(self, user, cached_data=None):
        """
        :param user:
        :param cached_data:
            user_shops
            user_subordinates
        """
        self.user = user
        self.cached_data = cached_data

    def has_permission(self):
        raise NotImplementedError


class BaseSingleWdPermissionChecker(BaseWdPermissionChecker):
    def _has_single_permission(self, employee_id, shop_id, action, graph_type, wd_type, wd_dt, is_vacancy):
        return GroupWorkerDayPermission.has_permission(
            user=self.user,
            action=action,
            graph_type=graph_type,
            wd_type=wd_type,
            wd_dt=wd_dt,
        ) and WorkerDay._has_group_permissions(
            self.user,
            employee_id,
            wd_dt,
            is_vacancy=is_vacancy,
            shop_id=shop_id,
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
        super(BaseSingleWdDataPermissionChecker, self).__init__(*args, **kwargs)

    def _has_single_wd_data_permission(self):
        return self._has_single_permission(
            employee_id=self.wd_data.get('employee_id'),
            shop_id=self.wd_data.get('shop_id'),
            action=self.action,
            graph_type=WorkerDayPermission.FACT if self.wd_data.get('is_fact') else WorkerDayPermission.PLAN,
            wd_type=self.wd_data.get('type'),
            wd_dt=self.wd_data.get('dt'),
            is_vacancy=self.wd_data.get('is_vacancy'),
        )


# class BaseListWdPermissionChecker(BaseWdPermissionChecker):  # TODO: зачем? получится?
#     pass


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

    def __init__(self, *args, wd_id, **kwargs):
        self.wd_id = wd_id
        super(UpdateSingleWdPermissionChecker, self).__init__(*args, **kwargs)

    def has_permission(self):
        return self._has_single_wd_data_permission()


class DeleteSingleWdPermissionChecker(BaseSingleWdPermissionChecker):
    action = WorkerDayPermission.DELETE

    def __init__(self, *args, wd_obj=None, wd_id=None, **kwargs):
        assert wd_obj or wd_id  # TODO: так?
        self.wd_obj = wd_obj
        self.wd_id = wd_id
        super(DeleteSingleWdPermissionChecker, self).__init__(*args, **kwargs)

    def has_permission(self):
        if not self.wd_obj:
            self.wd_obj = WorkerDay.objects.filter(id=self.wd_id).first()

        return self._has_single_permission(
            employee_id=self.wd_obj.employee_id,
            shop_id=self.wd_obj.shop_id,
            action=self.action,
            graph_type=WorkerDayPermission.FACT if self.wd_obj.is_fact else WorkerDayPermission.PLAN,
            wd_type=self.wd_obj.type,
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


# class UpdateQsWdPermissionChecker(BaseQsWdPermissionChecker):
#     pass  # TODO: используется?


class ApproveQsWdPermissionChecker(BaseQsWdPermissionChecker):
    action = WorkerDayPermission.APPROVE

    def __init__(self, *args, wd_qs, **kwargs):
        self.wd_qs = wd_qs
        super(ApproveQsWdPermissionChecker, self).__init__(*args, **kwargs)
