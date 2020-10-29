import os
from calendar import monthrange

from django.conf import settings
from django.db.models import Q, F, Prefetch
from django.utils.functional import cached_property

from src.base.models import Employment
from src.timetable.models import WorkerDay
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

    def _get_tabel_wdays_qs(self, fact_only=True):
        tabel_wdays = WorkerDay.objects.get_tabel(
            network=self.shop.network,
            fact_only=fact_only,
        ).filter(
            Q(
                type=WorkerDay.TYPE_WORKDAY,
                worker_day_details__work_type__shop=self.shop,
            ) |
            Q(
                type=WorkerDay.TYPE_QUALIFICATION,
                shop=self.shop,
            ) |
            Q(
                ~Q(type__in=WorkerDay.TYPES_TABEL_HOURS),
                Q(
                    Q(dt__lte=F('employment__dt_fired')) | Q(employment__dt_fired__isnull=True),
                    Q(dt__gte=F('employment__dt_hired')),
                    employment__shop=self.shop,
                ),
            ),
            dt__gte=self.dt_from,
            dt__lte=self.dt_to,
        )

        return tabel_wdays.select_related('worker', 'shop').order_by('worker__last_name', 'worker__first_name', 'dt')

    def get_data(self):
        raise NotImplementedError


class T13TabelDataGetter(BaseTabelDataGetter):
    wd_type_mapper_cls = T13WdTypeMapper

    def get_data(self):
        tabel_wdays = self._get_tabel_wdays_qs()
        tabel_employments = Employment.objects.filter(
            id__in=tabel_wdays.values_list('employment', flat=True).distinct()
        ).select_related(
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

        for num, empl in enumerate(tabel_employments, start=1):
            wdays = {_get_day_key(wd.dt.day): wd for wd in empl.tabel_worker_days}

            days = {}
            _weekday, days_in_month = monthrange(year=self.year, month=self.month)
            first_half_month_wdays = 0
            first_half_month_whours = 0
            second_half_month_wdays = 0
            second_half_month_whours = 0

            for day_num in range(1, days_in_month + 1):
                day_key = _get_day_key(day_num)
                day_data = days.setdefault(day_key, {})
                wday = wdays.get(day_key)
                day_data['code'] = self._get_tabel_type(wday.type) if wday else ''
                day_data['value'] = wday.tabel_work_hours if \
                    (wday and (WorkerDay.TYPE_WORKDAY or WorkerDay.TYPE_QUALIFICATION)) else ''
                days[day_key] = day_data
                if wday:
                    if wday.type == WorkerDay.TYPE_WORKDAY or WorkerDay.TYPE_QUALIFICATION:
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
                'fio_and_position': empl.get_short_fio_and_position(),
                'days': days,
                'first_half_month_wdays': first_half_month_wdays,
                'first_half_month_whours': first_half_month_whours,
                'second_half_month_wdays': second_half_month_wdays,
                'second_half_month_whours': second_half_month_whours,
                'full_month_wdays': first_half_month_wdays + second_half_month_wdays,
                'full_month_whours': first_half_month_whours + second_half_month_whours,
            }
            users.append(user_data)

        return {'users': users}


class MtsTabelDataGetter(BaseTabelDataGetter):
    def get_data(self):
        tabel_wdays = self._get_tabel_wdays_qs(fact_only=False)
        tabel_wdays = tabel_wdays.filter(
            type__in=WorkerDay.TYPES_TABEL_HOURS,
        )
        return {'tabel_wdays': tabel_wdays.select_related('worker', 'shop')}


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
        data = {
            'data': self.get_tabel_data(),
            'department_name': self.shop.name,
            'network_name': self.network.name,
            'network_okpo': self.network.okpo,
            'dt_from': self.dt_from.strftime('%d.%m.%Y'),
            'dt_to': self.dt_to.strftime('%d.%m.%Y'),
            'doc_num': f'{self.dt_to.month + 1}',
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


tabel_formats = {
    'default': MTSTabelGenerator,
    'mts': MTSTabelGenerator,
    't13': T13TabelGenerator,
    't13_custom': CustomT13TabelGenerator,
}


def get_tabel_generator_cls(tabel_format='default'):
    tabel_generator_cls = tabel_formats.get(tabel_format)
    return tabel_generator_cls
