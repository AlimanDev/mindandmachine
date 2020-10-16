import os
from calendar import monthrange
from collections import defaultdict

from django.conf import settings
from django.db.models import Q, F, Prefetch

from src.base.models import Employment
from src.timetable.models import WorkerDay
from .base import BaseDocGenerator


class TabelGenerator(BaseDocGenerator):
    """
    Базовый класс для генерации табеля
    """

    wd_type_to_t13_code_mapping = {
        WorkerDay.TYPE_WORKDAY: 'Я',
        WorkerDay.TYPE_HOLIDAY: 'В',
        WorkerDay.TYPE_BUSINESS_TRIP: 'К',
        WorkerDay.TYPE_VACATION: 'ОТ',
        # TODO: добавить оставльные
    }

    def __init__(self, shop, dt_from, dt_to):
        """
        :param shop: Подразделение, для сотрудников которого будет составляться табель
        :param dt_from: Дата от
        :param dt_to: Дата по
        """
        assert dt_from.year == dt_to.year and dt_from.month == dt_to.month

        self.year = dt_from.year
        self.month = dt_from.month

        self.network = shop.network
        self.shop = shop
        self.dt_from = dt_from
        self.dt_to = dt_to

    def get_template_path(self):
        raise NotImplementedError

    def get_data(self):
        data = {
            'users': self._get_users_and_days(),
            'department_name': self.shop.name,
            'network_name': self.network.name,
            'network_okpo': self.network.okpo,
            'dt_from': self.dt_from.strftime('%d.%m.%Y'),
            'dt_to': self.dt_to.strftime('%d.%m.%Y'),
            'doc_num': f'{self.dt_to.month + 1}',
        }
        return data

    @staticmethod
    def _get_day_key(day_num):
        return f'd{day_num}'

    @staticmethod
    def _get_fio_and_position(empl):
        fio_and_position = f'{empl.user.get_short_fio()}'
        if empl.position and empl.position.name:
            fio_and_position += f', {empl.position.name}'

        return fio_and_position

    @classmethod
    def _map_to_tabel_code(cls, wd_type):
        return cls.wd_type_to_t13_code_mapping.get(wd_type, '')

    def _get_users_and_days(self):
        active_shop_employments = Employment.objects.get_active(network_id=self.network.id, shop=self.shop)

        tabel_wdays = WorkerDay.objects.get_tabel(
            shop_id=self.shop.id,
        ).filter(
            Q(dt__lte=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True),
            Q(dt__gte=F('employment__dt_hired')),
            employment__in=active_shop_employments,
            dt__gte=self.dt_from,
            dt__lte=self.dt_to,
        )

        last_hired_empls_qs = active_shop_employments.last_hired().select_related(
            'user',
            'position',
        ).order_by(
            'user__last_name',
            'user__first_name',
        ).prefetch_related(
            Prefetch(
                'workerday_set',
                queryset=tabel_wdays.order_by(),
                to_attr='tabel_worker_days'
            )
        )

        users = []

        for num, empl in enumerate(last_hired_empls_qs, start=1):
            wdays = {self._get_day_key(wd.dt.day): wd for wd in empl.tabel_worker_days}

            days = {}
            _weekday, days_in_month = monthrange(year=self.year, month=self.month)
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0

            for day_num in range(1, days_in_month + 1):
                day_key = self._get_day_key(day_num)
                day_data = days.setdefault(day_key, {})
                wday = wdays.get(day_key)
                day_data['code'] = self._map_to_tabel_code(wday.type) if wday else ''
                day_data['value'] = wday.tabel_work_hours if wday and wday.type in WorkerDay.TYPES_PAID else ''
                days[day_key] = day_data
                if wday:
                    if wday.type == WorkerDay.TYPE_WORKDAY:
                        if day_num <= 15:  # первая половина месяца
                            first_half_month_wdays += 1
                            first_half_month_whours += wday.tabel_work_hours
                        else:
                            second_half_month_wdays += 1
                            second_half_month_whours += wday.tabel_work_hours

            user_data = {
                'num': num,
                'last_name': empl.user.last_name,
                'tabel_code': empl.user.tabel_code,
                'fio_and_position': self._get_fio_and_position(empl),
                'days': days,
                'first_half_month_wdays': first_half_month_wdays,
                'first_half_month_whours': first_half_month_whours,
                'second_half_month_wdays': second_half_month_wdays,
                'second_half_month_whours': second_half_month_whours,
                'full_month_wdays': first_half_month_wdays + second_half_month_wdays,
                'full_month_whours': first_half_month_whours + second_half_month_whours,
            }
            users.append(user_data)

        return users


class T13TabelGenerator(TabelGenerator):
    """
    Класс для генерации табеля в формате т-13
    """

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_13.ods')


class CustomTabelGenerator(TabelGenerator):
    """
    Класс для генерация табеля в кастомном формате.

    Note:
        Сделан для примера. Возможно нужна будет форма, где можно будет выводить большое количество сотрдуников.
    """

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_custom.ods')
