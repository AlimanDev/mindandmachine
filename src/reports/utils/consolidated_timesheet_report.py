import datetime
import io
import re
from collections import OrderedDict

import pandas as pd
from django.db.models import Q, F, Value, Case, When
from django.db.models import Sum
from django.db.models.functions import Concat
from django.utils.functional import cached_property

from src.base.models import (
    Employee,
    Employment,
)
from src.timetable.models import TimesheetItem
from src.timetable.models import WorkerDayType


class ConsolidatedTimesheetReportGenerator:
    def __init__(self, shop, dt_from: datetime.date, dt_to: datetime.date, group_by: list, cached_data=None):
        self.shop = shop
        self.dt_from = dt_from
        self.dt_to = dt_to
        self.group_by = group_by or ['employee']
        self.cached_data = cached_data or {}

    def _get_employees_qs(self):
        return Employee.objects.filter(
            id__in=Employment.objects.get_active_empl_by_priority(
                dt_from=self.dt_from,
                dt_to=self.dt_to,
                shop=self.shop,
            ).values_list('employee_id', flat=True)
        )

    @cached_property
    def columns_mapping(self):
        columns_mapping = OrderedDict()
        if 'employee' in self.group_by:
            columns_mapping['employee_fio'] = 'Сотрудник'
        if 'position' in self.group_by:
            columns_mapping['position__name'] = 'Должность'
        columns_mapping.update(OrderedDict(
            fact_total_hours='Итого рабочих часов',
            main_total_hours='Основной табель, рабочих ч',
            additional_total_hours='Дополнительный табель, рабочих ч',
        ))
        if 'employee' in self.group_by:
            for wd_type in self.show_stat_in_hours_wd_types:
                columns_mapping[wd_type.code] = wd_type.name + ', ч'
            columns_mapping['total_main_work_hours'] = 'Итого норма часов'
        return columns_mapping

    @cached_property
    def show_stat_in_hours_wd_types(self):
        return list(WorkerDayType.objects.filter(
            show_stat_in_hours=True,
            # Q(is_dayoff=True, is_work_hours=True) |  # TODO: или так?
            # Q(is_dayoff=False, is_work_hours=False)
        ).order_by(
            '-is_dayoff',
            '-ordering',
        ))

    def _get_annotations_dict(self):
        base_q = Q(
            day_type__is_dayoff=False,
            day_type__is_work_hours=True,
            source=TimesheetItem.SOURCE_TYPE_FACT,
        )
        fact_q = Q(base_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT)
        main_q = Q(base_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
        additional_q = Q(base_q, timesheet_type=TimesheetItem.TIMESHEET_TYPE_ADDITIONAL)
        annotations_dict = OrderedDict([
            ('fact_total_hours', Sum('day_hours', filter=fact_q) + Sum('night_hours', filter=fact_q)),
            ('main_total_hours', Sum('day_hours', filter=main_q) + Sum('night_hours', filter=main_q)),
            ('additional_total_hours', Sum('day_hours', filter=additional_q) + Sum('night_hours', filter=additional_q)),
        ])
        if 'employee' in self.group_by:
            annotations_dict['employee_fio'] = Concat(
                F('employee__user__last_name'), Value(' '),
                Case(When(employee__user__first_name__isnull=False,
                          then=Concat(F('employee__user__first_name'), Value(' '))), default=Value('')),
                Case(When(employee__user__middle_name__isnull=False,
                          then=Concat(F('employee__user__middle_name'), Value(' '))), default=Value('')),
            )
            for wd_type in self.show_stat_in_hours_wd_types:
                q = Q(day_type=wd_type)
                if wd_type.is_work_hours and wd_type.is_dayoff:
                    q &= Q(timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN)
                else:
                    q &= Q(
                        timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
                        source=TimesheetItem.SOURCE_TYPE_FACT,
                    )
                annotations_dict[wd_type.code] = Sum('day_hours', filter=q) + Sum('night_hours', filter=q)
            total_main_work_hours_q = Q(
                Q(day_type__is_dayoff=True) | Q(source=TimesheetItem.SOURCE_TYPE_FACT),
                day_type__is_work_hours=True,
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
            )
            annotations_dict['total_main_work_hours'] = \
                Sum('day_hours', filter=total_main_work_hours_q) + \
                Sum('night_hours', filter=total_main_work_hours_q)
        return annotations_dict

    def _get_order_by_list(self):
        order_by = []
        if 'employee' in self.group_by:
            order_by.append('employee__user__last_name')
            order_by.append('employee__user__first_name')
        if 'position' in self.group_by:
            order_by.append('position__name')
        return order_by

    def _get_data(self):
        annotations_dict = self._get_annotations_dict()
        data = list(TimesheetItem.objects.filter(
            Q(day_hours__gt=0) | Q(night_hours__gt=0),
            Q(day_type__is_dayoff=False, shop=self.shop) |
            Q(day_type__is_dayoff=True, employee__in=self._get_employees_qs()),
            dt__gte=self.dt_from,
            dt__lte=self.dt_to,
        ).values(
            *self.group_by,
        ).annotate(
            **annotations_dict,
        ).values_list(
            *self.columns_mapping.keys(),
        ).order_by(
            *self._get_order_by_list(),
        ))
        return data

    @staticmethod
    def get_col_widths(dataframe):
        # max of the lengths of column name and its values for each column, left to right
        return [max([len(str(s)) for s in dataframe[col].values] + [len(col)]) + 2 for col in dataframe.columns]

    def _beatufy_report(self, df, writer, sheet_name):
        workbook = writer.book
        worksheet = writer.sheets[sheet_name]
        worksheet.set_row(0, 40)
        for i, width in enumerate(self.get_col_widths(df)):
            worksheet.set_column(i, i, width)
        title_merge_f = workbook.add_format({
            'bold': 1,
            'align': 'center',
            'valign': 'vcenter',
            'font': 14,
        })
        worksheet.merge_range('A1:D1', 'Консолидированный отчет об отработанном времени', title_merge_f)
        worksheet.write('A2', 'Наименование объекта')
        worksheet.merge_range('B2:D2', f'{self.shop.name}')
        worksheet.write('A3', 'Период')
        worksheet.merge_range('B3:D3', f'{self.dt_from.strftime("%Y.%m.%d")} - {self.dt_to.strftime("%Y.%m.%d")}')
        worksheet.write(f'A{len(df.index) + 4}', 'Итого часов')

    def generate(self, sheet_name):
        sheet_name = re.sub(r'[\[\]:*?/\\]', '', sheet_name)
        data = self._get_data()
        df = pd.DataFrame(data, columns=self.columns_mapping.values()).fillna('')
        df = df.apply(pd.to_numeric, errors='ignore', downcast='float')
        df.loc['Total'] = df.sum(numeric_only=True, axis=0).replace(0, '')
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        df.to_excel(
            excel_writer=writer, sheet_name=sheet_name, index=False, startrow=3,
        )
        self._beatufy_report(df, writer, sheet_name)
        writer.book.close()
        output.seek(0)
        return output
