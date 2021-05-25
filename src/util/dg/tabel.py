import os
from calendar import monthrange
from datetime import datetime

from django.conf import settings
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from src.base.models import Employment
from src.timetable.models import WorkerDay, PlanAndFactHours
from src.util.dg.helpers import MONTH_NAMES
from .base import BaseDocGenerator


def _get_day_key(day_num):
    return f'd{day_num}'


class BaseWdTypeMapper:
    wd_type_to_tabel_type_mapping = None

    def get_tabel_type(self, wd_type):
        return self.wd_type_to_tabel_type_mapping.get(wd_type) or ''


class DummyWdTypeMapper(BaseWdTypeMapper):
    wd_type_to_tabel_type_mapping = {}


class T13WdTypeMapper(BaseWdTypeMapper):
    wd_type_to_tabel_type_mapping = {
        WorkerDay.TYPE_WORKDAY: 'Я',
        WorkerDay.TYPE_HOLIDAY: 'В',
        WorkerDay.TYPE_BUSINESS_TRIP: 'К',
        WorkerDay.TYPE_VACATION: 'ОТ',
        WorkerDay.TYPE_SELF_VACATION: 'ДО',
        WorkerDay.TYPE_MATERNITY: 'ОЖ',
        WorkerDay.TYPE_SICK: 'Б',
        # TODO: добавить оставльные
    }


class BaseTabelDataGetter:
    wd_type_mapper_cls = DummyWdTypeMapper

    def __init__(self, shop, dt_from, dt_to):
        self.year = dt_from.year
        self.month = dt_from.month

        self.network = shop.network
        self.shop = shop
        self.dt_from = dt_from
        self.dt_to = dt_to

    @cached_property
    def wd_type_mapper(self):
        return self.wd_type_mapper_cls()

    def _get_tabel_type(self, wd_type):
        return self.wd_type_mapper.get_tabel_type(wd_type)

    def _get_tabel_wdays_qs(self):
        tabel_wdays = WorkerDay.objects.get_tabel().filter(
            Q(
                type__in=WorkerDay.TYPE_WORKDAY,
                shop=self.shop,
                worker_day_details__work_type__shop=self.shop,
            ) |
            Q(
                type__in=[WorkerDay.TYPE_QUALIFICATION, WorkerDay.TYPE_BUSINESS_TRIP],
                shop=self.shop,
            ) |
            Q(
                ~Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE),
                Q(employee__in=Employment.objects.get_active(
                    network_id=self.network.id,
                    dt_from=self.dt_from,
                    dt_to=self.dt_to,
                    shop=self.shop,
                ).distinct().values_list('employee', flat=True))
            ),
            dt__gte=self.dt_from,
            dt__lte=self.dt_to,
        )

        return tabel_wdays.select_related(
            'employee__user',
            'shop',
            'employment',
        ).order_by(
            'employee__user__last_name',
            'employee__user__first_name',
            'employee_id',
            'dt',
        )


    def get_data(self):
        raise NotImplementedError


class T13TabelDataGetter(BaseTabelDataGetter):
    wd_type_mapper_cls = T13WdTypeMapper

    def set_day_data(self, day_data, wday):
        day_data['code'] = self._get_tabel_type(wday.type) if wday else ''
        day_data['value'] = wday.rounded_work_hours if \
            (wday and wday.type in WorkerDay.TYPES_WITH_TM_RANGE) else ''

    def get_data(self):

        def _get_active_empl(wd, empls):
            if not wd.employment:
                return list(filter(
                    lambda e: (e.dt_hired is None or e.dt_hired <= wd.dt) and (
                                e.dt_fired is None or wd.dt <= e.dt_fired),
                    empls.get(wd.employee_id, []),
                ))[0]
            return wd.employment

        tabel_wdays = self._get_tabel_wdays_qs()

        empls = {}
        empls_qs = Employment.objects.get_active(
            dt_from=self.dt_from,
            dt_to=self.dt_to,
            employee__id__in=tabel_wdays.values_list('employee', flat=True),
        ).annotate_value_equality(
            'is_equal_shops', 'shop_id', self.shop.id,
        ).select_related(
            'employee',
            'employee__user',
            'position',
        ).order_by('-is_equal_shops')
        for e in empls_qs:
            empls.setdefault(e.employee_id, []).append(e)

        num = 1

        users = []
        grouped_worker_days = {}
        for wd in tabel_wdays:
            if wd.type in WorkerDay.TYPES_WITH_TM_RANGE and not _get_active_empl(wd, empls):
                continue
            grouped_worker_days.setdefault(wd.employee_id, []).append(wd)

        for employee_id, wds in grouped_worker_days.items():
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0
            days = {}
            for wd in wds:
                day_key = _get_day_key(wd.dt.day)
                day_data = days.setdefault(day_key, {})
                self.set_day_data(day_data, wd)
                days[day_key] = day_data
                if wd.type in WorkerDay.TYPES_WITH_TM_RANGE:
                    if wd.dt.day <= 15:  # первая половина месяца
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.rounded_work_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.rounded_work_hours
            e = sorted(empls.get(employee_id), key=lambda x: x.dt_fired or datetime.max.date(), reverse=True)[0]
            user_data = {
                'num': num,
                'last_name': e.employee.user.last_name,
                'tabel_code': e.employee.tabel_code,
                'fio_and_position': e.get_short_fio_and_position(),
                'fio': e.employee.user.fio,
                'position': e.position.name if e.position else '',
                'days': days,
                'first_half_month_wdays': first_half_month_wdays,
                'first_half_month_whours': first_half_month_whours,
                'second_half_month_wdays': second_half_month_wdays,
                'second_half_month_whours': second_half_month_whours,
                'full_month_wdays': first_half_month_wdays + second_half_month_wdays,
                'full_month_whours': first_half_month_whours + second_half_month_whours,
            }
            users.append(user_data)
            num += 1

        for user_data in users:
            for day_num in range(1, 31 + 1):
                day_key = _get_day_key(day_num)
                if day_key not in user_data['days']:
                    day_data = user_data['days'].setdefault(day_key, {})
                    self.set_day_data(day_data, None)

        return {'users': users}


class MtsTabelDataGetter(BaseTabelDataGetter):
    def get_data(self):
        return {
            'plan_and_fact_hours': PlanAndFactHours.objects.filter(
                shop=self.shop,
                wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE,
                dt__gte=self.dt_from,
                dt__lte=self.dt_to,
            ).distinct(),
        }


class AigulTabelDataGetter(T13TabelDataGetter):
    def set_day_data(self, day_data, wday):
        day_data['value'] = wday.rounded_work_hours if \
            (wday and wday.type in WorkerDay.TYPES_WITH_TM_RANGE) else self._get_tabel_type(wday.type) if wday else ''


class BaseTabelGenerator(BaseDocGenerator):
    """
    Базовый класс для генерации табеля
    """

    tabel_data_getter_cls = None

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
        dt_from = self.dt_from.strftime('%d.%m.%Y')
        dt_to = self.dt_to.strftime('%d.%m.%Y')
        month_name = MONTH_NAMES[self.dt_from.month]
        year = self.dt_from.year
        data = {
            'data': self.get_tabel_data(),
            'department_name': self.shop.name,
            'network_name': self.network.name,
            'network_okpo': self.network.okpo,
            'dt_from': dt_from,
            'dt_to': dt_to,
            'doc_num': f'{self.dt_to.month + 1}',
            'month_name': month_name,
            'year': year,
            'tabel_text': _('Tabel for {} {}y').format(month_name, year),
        }
        return data

    @classmethod
    def map_wd_type_to_tabel_type(cls, wd_type):
        raise NotImplementedError

    def get_tabel_data(self):
        table_data_getter = self.tabel_data_getter_cls(self.shop, self.dt_from, self.dt_to)
        return table_data_getter.get_data()


class T13TabelGenerator(BaseTabelGenerator):
    """
    Класс для генерации табеля в формате т-13
    """
    tabel_data_getter_cls = T13TabelDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_13.ods')


class CustomT13TabelGenerator(T13TabelGenerator):
    """
    Класс для генерация табеля в кастомном формате (производном от Т-13).

    Note:
        Сделан для примера. Возможно нужна будет форма, где можно будет выводить большое количество сотрдуников.
    """

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_custom.ods')


class MTSTabelGenerator(BaseTabelGenerator):
    """
    Класс для генерация табеля в формате МТС.

    Note:
        Заготовка.
    """

    tabel_data_getter_cls = MtsTabelDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_mts.ods')


class AigulTabelGenerator(BaseTabelGenerator):
    """
    Шаблон табеля для Айгуль
    """

    tabel_data_getter_cls = AigulTabelDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_aigul.ods')


tabel_formats = {
    'default': MTSTabelGenerator,
    'mts': MTSTabelGenerator,
    't13': T13TabelGenerator,
    't13_custom': CustomT13TabelGenerator,
    'aigul': AigulTabelGenerator,
}


def get_tabel_generator_cls(tabel_format='default'):
    tabel_generator_cls = tabel_formats.get(tabel_format)
    return tabel_generator_cls
