from collections import OrderedDict
from datetime import timedelta
from decimal import Decimal

from django.db import transaction

from src.timetable.models import (
    Employment as EmploymentModel,
    TimesheetItem as TimesheetItemModel,
)


class TimesheetItem:
    def __init__(self, dt, shop, position, day_type,
                 day_hours=None, night_hours=None,
                 work_type_name=None, dttm_work_start=None, dttm_work_end=None, source=None):
        self.dt = dt
        self.shop = shop
        self.position = position
        self.work_type_name = work_type_name
        self.day_type = day_type
        self.day_hours = Decimal(day_hours) if day_hours else Decimal('0.00')
        self.night_hours = Decimal(night_hours) if night_hours else Decimal('0.00')
        self.dttm_work_start = dttm_work_start
        self.dttm_work_end = dttm_work_end
        self.source = source

    @property
    def total_hours(self):
        return self.day_hours + self.night_hours

    def copy(self, overrides=None):
        kwargs = dict(
            dt=self.dt,
            shop=self.shop,
            position=self.position,
            work_type_name=self.work_type_name,
            day_type=self.day_type,
            day_hours=self.day_hours,
            night_hours=self.night_hours,
            dttm_work_start=self.dttm_work_start,
            dttm_work_end=self.dttm_work_end,
        )
        if overrides:
            kwargs.update(overrides)
        return TimesheetItem(**kwargs)

    def subtract_hours(self, hours_to_subtract, fields=None):
        assert self.total_hours > hours_to_subtract
        hours_left_to_subtract = hours_to_subtract
        fields = fields or ['night_hours', 'day_hours']
        subtracted_item = self.copy(overrides=dict(
            day_hours=Decimal('0.00'),
            night_hours=Decimal('0.00'),
        ))
        for field in fields:
            field_hours = getattr(self, field)
            if field_hours > 0:
                if field_hours > hours_left_to_subtract:
                    setattr(self, field, field_hours - hours_left_to_subtract)
                    if not self.day_type.is_dayoff:
                        new_dttm_work_end = self.dttm_work_end - timedelta(hours=float(hours_left_to_subtract))
                        self.dttm_work_end = new_dttm_work_end
                        subtracted_item.dttm_work_start = new_dttm_work_end
                    setattr(subtracted_item, field,
                            getattr(subtracted_item, field) + hours_left_to_subtract)
                    break
                else:
                    setattr(self, field, Decimal('0.00'))
                    if not self.day_type.is_dayoff:
                        new_dttm_work_end = self.dttm_work_end - timedelta(hours=float(field_hours))
                        self.dttm_work_end = new_dttm_work_end
                        subtracted_item.dttm_work_start = new_dttm_work_end
                    setattr(subtracted_item, field, getattr(subtracted_item, field) + field_hours)
                    hours_left_to_subtract = hours_left_to_subtract - field_hours
        return subtracted_item


class Timesheet:
    def __init__(self, fiscal_timesheet, timesheet_type):
        self.fiscal_timesheet = fiscal_timesheet
        self._timesheet_items = OrderedDict()
        self.timesheet_type = timesheet_type

    def _get_hours_sum(self, dt, fields, filter_func=None):
        hours_sum = Decimal('0.00')
        timesheet_items = self.get_items(dt=dt, filter_func=filter_func)
        for timesheet_item in timesheet_items:
            for field in fields:
                hours_sum += getattr(timesheet_item, field, None) or Decimal('0.00')
        return hours_sum

    def get_items(self, dt=None, filter_func=None):
        items = self._timesheet_items.get(dt, []) if dt else list(
            item for sublist in self._timesheet_items.values() for item in sublist)
        if filter_func:
            items = list(filter(filter_func, items))
        return items

    def is_holiday(self, dt):
        items = self.get_items(dt=dt)
        return not items or \
               any((item.day_type.is_dayoff and not item.day_type.is_work_hours) for item in items) or \
               self.get_total_hours_sum(dt=dt) == 0

    def get_day_hours_sum(self, dt=None, filter_func=None):
        return self._get_hours_sum(dt=dt, filter_func=filter_func, fields=['day_hours'])

    def get_night_hours_sum(self, dt=None, filter_func=None):
        return self._get_hours_sum(dt=dt, filter_func=filter_func, fields=['night_hours'])

    def get_total_hours_sum(self, dt=None, filter_func=None):
        return self._get_hours_sum(dt=dt, filter_func=filter_func, fields=['day_hours', 'night_hours'])

    def add(self, dt, timesheet_item):
        if isinstance(timesheet_item, list):
            for item in timesheet_item:
                self._timesheet_items.setdefault(dt, []).append(item)
        elif isinstance(timesheet_item, TimesheetItem):
            self._timesheet_items.setdefault(dt, []).append(timesheet_item)
        else:
            raise ValueError('timesheet_item should be TimesheetItem object or list of TimesheetItem objects')

    def pop(self, dt):
        return self._timesheet_items.pop(dt)

    def remove(self, dt, item):
        return self._timesheet_items[dt].remove(item)

    def subtract_hours(self, dt, hours_to_subtract, filters=None):
        items = self.pop(dt)
        subtracted_items = []
        hours_left_to_subtract = hours_to_subtract
        for item in items:
            if filters:
                if not all(getattr(item, k) == v for k, v in filters.items()):
                    continue
            if hours_left_to_subtract > item.total_hours:
                items.remove(item)
                subtracted_items.append(item)
                hours_left_to_subtract = hours_left_to_subtract - item.total_hours
            else:
                subtracted_item = item.subtract_hours(hours_to_subtract=hours_left_to_subtract)
                subtracted_items.append(subtracted_item)
        if items:
            self.add(dt, items)
        return subtracted_items

    def save(self):
        timesheet_items = []
        for dt, items in self._timesheet_items.items():
            for i in items:
                timesheet_items.append(
                    TimesheetItemModel(
                        timesheet_type=self.timesheet_type,
                        employee=self.fiscal_timesheet.employee,
                        dt=dt,
                        shop=i.shop,
                        position=i.position,
                        work_type_name=i.work_type_name,
                        day_type=i.day_type,
                        dttm_work_start=i.dttm_work_start,
                        dttm_work_end=i.dttm_work_end,
                        day_hours=i.day_hours,
                        night_hours=i.night_hours,
                        source=i.source or '',
                    )
                )
        TimesheetItemModel.objects.bulk_create(timesheet_items)


class FiscalTimesheet:
    def __init__(self, employee, dt_from, dt_to, wd_types_dict):
        self.wd_types_dict = wd_types_dict
        self.employee = employee
        self.active_employments = list(EmploymentModel.objects.get_active(
            network_id=employee.user.network_id,
            dt_from=dt_from,
            dt_to=dt_to,
            employee=employee,
        ).select_related(
            'shop',
            'employee__user',
            'position',
        ))
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.fact_timesheet = Timesheet(self, timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_FACT)
        self.main_timesheet = Timesheet(self, timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_MAIN)
        self.additional_timesheet = Timesheet(self, timesheet_type=TimesheetItemModel.TIMESHEET_TYPE_ADDITIONAL)
        self._cached_data = {}

    def _get_active_employment(self, dt):
        active_employment = self._cached_data.setdefault('active_employments', {}).get(dt)
        if active_employment:
            return active_employment

        for active_employment in self.active_employments:
            if active_employment.is_active(dt=dt):
                self._cached_data.setdefault('active_employments', {})[dt] = active_employment
                return active_employment

    def init_fact_timesheet(self, fact_timesheet_data):
        for dt, fact_timesheet_data_items in fact_timesheet_data.items():
            for fact_timesheet_item_dict in fact_timesheet_data_items:
                self.fact_timesheet.add(dt, TimesheetItem(
                    dt=fact_timesheet_item_dict.get('dt'),
                    shop=fact_timesheet_item_dict.get('shop'),
                    position=fact_timesheet_item_dict.get('position'),
                    work_type_name=fact_timesheet_item_dict.get('work_type_name'),
                    day_type=self.wd_types_dict[fact_timesheet_item_dict.get('fact_timesheet_type_id')],
                    day_hours=fact_timesheet_item_dict.get('fact_timesheet_day_hours'),
                    night_hours=fact_timesheet_item_dict.get('fact_timesheet_night_hours'),
                    dttm_work_start=fact_timesheet_item_dict.get('fact_timesheet_dttm_work_start'),
                    dttm_work_end=fact_timesheet_item_dict.get('fact_timesheet_dttm_work_end'),
                    source=fact_timesheet_item_dict.get('fact_timesheet_source'),
                ))

    def save(self):
        with transaction.atomic():
            TimesheetItemModel.objects.filter(
                employee=self.employee,
                dt__gte=self.dt_from,
                dt__lte=self.dt_to,
            ).delete()
            self.fact_timesheet.save()
            self.main_timesheet.save()
            self.additional_timesheet.save()
