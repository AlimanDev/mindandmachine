import os
from datetime import datetime

from django.conf import settings
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext as _

from src.base.models import Employment
from src.timetable.models import TimesheetItem, WorkerDay, PlanAndFactHours, WorkerDayType
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
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.wd_type_to_tabel_type_mapping = dict(WorkerDayType.objects.values_list('code', 'excel_load_code'))


class BaseTimesheetDataGetter:
    wd_type_mapper_cls = DummyWdTypeMapper

    def __init__(self, shop, dt_from, dt_to, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT, wd_types_dict=None):
        self.year = dt_from.year
        self.month = dt_from.month

        self.network = shop.network
        self.shop = shop
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.timesheet_type = timesheet_type
        self.wd_types_dict = wd_types_dict or WorkerDayType.get_wd_types_dict()

    @cached_property
    def wd_type_mapper(self):
        return self.wd_type_mapper_cls()

    def _get_tabel_type(self, wd_type):
        return self.wd_type_mapper.get_tabel_type(wd_type.code)

    def _get_timesheet_qs(self):
        timesheet_qs = TimesheetItem.objects.filter(
            dt__gte=self.dt_from,
            dt__lte=self.dt_to,
            timesheet_type=self.timesheet_type,
        ).select_related(
            'day_type',
        )

        wdays_q = Q()

        if self.shop.network.settings_values_prop.get('timesheet_include_curr_shop_wdays', True):
            wdays_q |= Q(
                day_type__is_dayoff=False,
                shop=self.shop,
            )

        if self.shop.network.settings_values_prop.get('timesheet_include_curr_shop_employees_wdays', True):
            shop_employees_part_q = Q(Q(shop=self.shop) | Q(day_type__is_dayoff=True))
            if self.shop.network.settings_values_prop.get('tabel_include_other_shops_wdays', False):
                shop_employees_part_q |= Q(Q(day_type__is_dayoff=False) & ~Q(shop=self.shop))

            employment_extra_q = Q()
            if self.shop.network.settings_values_prop.get('timesheet_exclude_invisible_employments', True):
                employment_extra_q &= Q(
                    is_visible=True,
                )

            wdays_q |= Q(
                shop_employees_part_q,
                Q(employee__in=Employment.objects.get_active(
                    network_id=self.network.id,
                    dt_from=self.dt_from,
                    dt_to=self.dt_to,
                    shop=self.shop,
                    extra_q=employment_extra_q,
                ).distinct().values_list('employee', flat=True))
            )

        if wdays_q:
            timesheet_qs = timesheet_qs.filter(wdays_q)
        else:
            timesheet_qs = TimesheetItem.objects.none()

        return timesheet_qs.select_related(
            'employee__user',
            'shop',
            'position',
        ).order_by(
            'employee__user__last_name',
            'employee__user__first_name',
            'employee_id',
            'dt',
        )

    def get_data(self):
        raise NotImplementedError


class T13TimesheetDataGetter(BaseTimesheetDataGetter):
    wd_type_mapper_cls = T13WdTypeMapper

    def set_day_data(self, day_data, wday):
        day_data['code'] = self._get_tabel_type(wday.day_type) if wday else ''
        day_data['value'] = (wday.day_hours + wday.night_hours) if \
            (wday and not wday.day_type.is_dayoff) else ''

    def get_extra_grouping_attrs(self):
        pass

    def _get_grouping_attrs(self):
        grouping_attrs = [
            'employee_id',  # должен быть всегда
        ]
        extra_grouping_attrs = self.get_extra_grouping_attrs()
        if extra_grouping_attrs:
            grouping_attrs.extend(extra_grouping_attrs)
        return grouping_attrs

    def _get_user_key_func(self):
        return lambda wd: tuple(getattr(wd, attr_name) for attr_name in self._get_grouping_attrs())

    def get_shop_name(self, e, ts_items):
        return e.shop.name if e.shop else ''

    def get_position_name(self, e, ts_items):
        return e.position.name if e.position else ''

    def get_data(self):
        def _get_active_empl(wd, empls):
            active_empls = list(filter(
                lambda e: (e.dt_hired is None or e.dt_hired <= wd.dt) and (
                            e.dt_fired is None or wd.dt <= e.dt_fired),
                empls.get(wd.employee_id, []),
            ))
            if active_empls:
                return active_empls[0]

        timesheet_qs = self._get_timesheet_qs()

        empls = {}
        empls_qs = Employment.objects.get_active(
            dt_from=self.dt_from,
            dt_to=self.dt_to,
            employee__id__in=timesheet_qs.values_list('employee', flat=True),
        ).annotate_value_equality(
            'is_equal_shops', 'shop_id', self.shop.id,
        ).select_related(
            'employee',
            'employee__user',
            'position',
            'shop',
        ).order_by('-is_equal_shops')
        for e in empls_qs:
            empls.setdefault(e.employee_id, []).append(e)

        num = 1

        users = []
        grouped_worker_days = {}
        get_user_key_func = self._get_user_key_func()
        for wd in timesheet_qs:
            if not wd.day_type.is_dayoff and not _get_active_empl(wd, empls):
                continue
            grouped_worker_days.setdefault(get_user_key_func(wd), []).append(wd)

        for grouped_attrs, wds in grouped_worker_days.items():
            employee_id = grouped_attrs[0]
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
                if not wd.day_type.is_dayoff:
                    if wd.dt.day <= 15:  # первая половина месяца
                        first_half_month_wdays += 1
                        first_half_month_whours += wd.day_hours + wd.night_hours
                    else:
                        second_half_month_wdays += 1
                        second_half_month_whours += wd.day_hours + wd.night_hours
            e = sorted(empls.get(employee_id), key=lambda x: x.dt_fired or datetime.max.date(), reverse=True)[0]
            user_data = {
                'num': num,
                'last_name': e.employee.user.last_name,
                'tabel_code': e.employee.tabel_code,
                'fio_and_position': e.get_short_fio_and_position(),
                'fio': e.employee.user.fio,
                'position': self.get_position_name(e, wds),
                'shop': self.get_shop_name(e, wds),
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

        work_hours_sum = 0
        work_days_sum = 0
        for user_data in users:
            work_days_sum += user_data['full_month_wdays']
            work_hours_sum += user_data['full_month_whours']
            for day_num in range(1, 31 + 1):
                day_key = _get_day_key(day_num)
                if day_key not in user_data['days']:
                    day_data = user_data['days'].setdefault(day_key, {})
                    self.set_day_data(day_data, None)

        return {
            'users': users,
            'work_hours_sum': work_hours_sum,
            'work_days_sum': work_days_sum,
        }


class MtsTimesheetDataGetter(BaseTimesheetDataGetter):
    def get_data(self):
        shop_q = Q(shop=self.shop)
        if self.shop.network.settings_values_prop.get('tabel_include_other_shops_wdays', False):
            shop_q |= Q(
                Q(
                    Q(wd_type_id=WorkerDay.TYPE_WORKDAY) & ~Q(shop=self.shop)
                ) &
                Q(employee__in=Employment.objects.get_active(
                    network_id=self.network.id,
                    dt_from=self.dt_from,
                    dt_to=self.dt_to,
                    shop=self.shop,
                ).distinct().values_list('employee', flat=True))
            )

        return {
            'plan_and_fact_hours': PlanAndFactHours.objects.filter(
                shop_q,
                wd_type__is_dayoff=False,
                dt__gte=self.dt_from,
                dt__lte=self.dt_to,
            ).distinct(),
        }


class AigulTimesheetDataGetter(T13TimesheetDataGetter):
    def set_day_data(self, day_data, wday):
        day_data['value'] = (wday.day_hours + wday.night_hours) if (
                    wday and not wday.day_type.is_dayoff) else self._get_tabel_type(wday.day_type) if wday else ''


class TimesheetLinesDataGetter(AigulTimesheetDataGetter):
    def set_day_data(self, day_data, wday):
        if not wday:
            day_data['value'] = ''
            return

        if not wday.day_type.is_dayoff:
            day_data['value'] = wday.day_hours + wday.night_hours
        elif wday.day_type.is_dayoff and wday.day_type.is_work_hours:
            day_data['value'] = self._get_tabel_type(wday.day_type) + ' ' + '{0:g}'.format(
                float(wday.day_hours + wday.night_hours))
        else:
            day_data['value'] = self._get_tabel_type(wday.day_type)

    def get_extra_grouping_attrs(self):
        return [
            'position_id',
            'shop_id',
        ]

    def get_shop_name(self, e, ts_items):
        return ts_items[0].shop.name if ts_items and ts_items[0].shop_id else ''

    def get_position_name(self, e, ts_items):
        return ts_items[0].position.name if ts_items and ts_items[0].position_id else ''


class BaseTimesheetGenerator(BaseDocGenerator):
    """
    Базовый класс для генерации табеля
    """

    tabel_data_getter_cls = None

    def __init__(self, shop, dt_from, dt_to, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT):
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
        self.timesheet_type = timesheet_type

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
            'tabel_cell_names': {
                'fio': _('Full name'),
                'num_in_order': _('Number in order'),
                'fio_initials_position': _('Last name, initials, position (specialty, profession)'),
                'tabel_code': _('Employee id'),
                'attendance_notes': _('Notes on attendance and non-attendance at work on the dates of the month'),
                'worked_out_for': _('Worked out for'),
                'half_of_the_month': _('half of the month (I, II)'),
                'month': _('month'),
                'days': _('Days'),
                'hours': _('Hours'),
                'position': _('Position'),
                'shop': _('Shop'),
                'total_hours': _('Total hours'),
                'total_days': _('Total days'),
                'date': _('Date'),
                'shop_code': _('Shop code'),
                'shop_name': _('Shop name'),
                'work_type_name': _('Work type'),
                'fact_h': _('Fact, h'),
                'plan_h': _('Plan, h'),
                'dttm_work_start_fact_h': _('Shift start time, fact, h'),
                'dttm_work_end_fact_h': _('Shift end time, fact, h'),
                'dttm_work_start_plan_h': _('Shift start time, plan, h'),
                'dttm_work_end_plan_h': _('Shift end time, plan, h'),
            },
        }
        return data

    @classmethod
    def map_wd_type_to_tabel_type(cls, wd_type):
        raise NotImplementedError

    def get_tabel_data(self):
        table_data_getter = self.tabel_data_getter_cls(self.shop, self.dt_from, self.dt_to, timesheet_type=self.timesheet_type)
        return table_data_getter.get_data()


class T13TimesheetGenerator(BaseTimesheetGenerator):
    """
    Класс для генерации табеля в формате т-13
    """
    tabel_data_getter_cls = T13TimesheetDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_13.ods')


class CustomT13TimesheetGenerator(T13TimesheetGenerator):
    """
    Класс для генерация табеля в кастомном формате (производном от Т-13).

    Note:
        Сделан для примера. Возможно нужна будет форма, где можно будет выводить большое количество сотрдуников.
    """

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_custom.ods')


class MTSTimesheetGenerator(BaseTimesheetGenerator):
    """
    Класс для генерация табеля в формате МТС.

    Note:
        Заготовка.
    """

    tabel_data_getter_cls = MtsTimesheetDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_mts.ods')


class AigulTimesheetGenerator(BaseTimesheetGenerator):
    """
    Шаблон табеля для Айгуль
    """

    tabel_data_getter_cls = AigulTimesheetDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_aigul.ods')


class TimesheetLinesGenerator(BaseTimesheetGenerator):
    """
    Шаблон табеля построчно -- сотрудник, должность, подразделение выхода
    """

    tabel_data_getter_cls = TimesheetLinesDataGetter

    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/t_lines.ods')


tabel_formats = {  # TODO: поменять имена клиентов на какие-то общие названия
    'default': MTSTimesheetGenerator,
    'mts': MTSTimesheetGenerator,
    't13': T13TimesheetGenerator,
    't13_custom': CustomT13TimesheetGenerator,
    'aigul': AigulTimesheetGenerator,
    'lines': TimesheetLinesGenerator,
}


def get_tabel_generator_cls(tabel_format='default'):
    tabel_generator_cls = tabel_formats.get(tabel_format)
    return tabel_generator_cls
