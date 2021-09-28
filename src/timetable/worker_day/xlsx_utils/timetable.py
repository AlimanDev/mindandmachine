from datetime import datetime, timedelta
from math import ceil

from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext as _

from src.base.models import (
    Employment,
    User,
    ProductionDay,
    Employee,
)
from src.conf.djconfig import QOS_SHORT_TIME_FORMAT
from src.timetable.models import (
    WorkerDay,
    WorkerDayType,
)
from src.timetable.worker_day.xlsx_utils.colors import *
from src.timetable.worker_day.xlsx_utils.tabel import Tabel_xlsx
from src.util.dg.helpers import MONTH_NAMES


class Cell(object):
    def __init__(self, dttm, format=None):
        self.dttm = dttm
        self.format = format


def fmt(**kwargs):
    kwargs.setdefault('align', 'center')
    kwargs.setdefault('valign', 'vcenter')
    kwargs.setdefault('text_wrap', True)
    return kwargs


def fmt2(**kwargs):
    kwargs.setdefault('align', 'center')
    kwargs.setdefault('valign', 'vcenter')
    kwargs.setdefault('text_wrap', True)
    kwargs.setdefault('top', 1)
    kwargs.setdefault('bottom', 1)
    kwargs.setdefault('left', 1)
    kwargs.setdefault('right', 1)
    return kwargs


def fmt3(**kwargs):
    kwargs.setdefault('align', 'center')
    kwargs.setdefault('valign', 'vcenter')
    kwargs.setdefault('text_wrap', True)
    kwargs.setdefault('font_name', 'Arial Cyr')
    return kwargs


class Timetable_xlsx(Tabel_xlsx):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_type = {
            'font_size': 14 if not self.on_print else 6,
            'font_name': 'Arial',
            'bold': False,
            'align': 'center',
            'valign': 'vcenter',
            'border': 1,
            'text_wrap': True,
        }

    def format_cells(self, users_len):
        super().format_cells(users_len)

        def set_rows(row1, row2, heigth):
            for row in range(row1, row2 + 1):
                self.worksheet.set_row(row, heigth)

        normalized = 6.23820623

        self.worksheet.set_column(3, 3, 15 if not self.on_print else 7 / normalized)
        self.worksheet.set_column(4, 5, 40 / normalized)
        self.worksheet.set_column(4, 36, 60 / normalized)
        #self.worksheet.set_column(37, 37, 150 / normalized)
        self.worksheet.set_column(37, 39, 60 / normalized)

        normalized_row = 1
        set_rows(10, 10, 15 / normalized_row)
        set_rows(11, 11 + users_len, 35 / normalized_row)

    def add_main_info(self):
        # format
        format_header_text = self.workbook.add_format(fmt(font_size=10, border=2))
        format_meta_bold = self.workbook.add_format(fmt(font_size=11, bold=True, align='left', text_wrap=False))
        format_meta_bold_bottom = self.workbook.add_format(
            fmt(font_size=11, bold=True, align='left', text_wrap=False, bottom=1))
        format_meta_bold_bottom_2 = self.workbook.add_format(
            fmt(font_size=11, bold=True, align='left', text_wrap=False, bottom=2))
        format_meta_bold_left_small = self.workbook.add_format(
            fmt(font_size=9, bold=True, align='left', text_wrap=False))
        format_meta_bold_right_small = self.workbook.add_format(
            fmt(font_size=9, bold=True, align='right', text_wrap=False))

        # top left info
        self.worksheet.write_string(2, 1, _('Shop: {}').format(self.shop.name), format_meta_bold)
        self.worksheet.write_rich_string(3, 1, _('Employee work timetable'), format_meta_bold_bottom_2)
        self.worksheet.write_rich_string(3, 2, format_meta_bold,
                                         _('{}  {}y.').format(MONTH_NAMES[self.month.month].upper(), self.month.year))
        self.worksheet.write_string(6, 2, '', format_meta_bold_bottom)
        self.worksheet.write_string(6, 1, _('Created by: '), format_meta_bold_bottom)
        self.worksheet.write_string(7, 1, _('signature'), format_meta_bold_right_small)
        self.worksheet.write_string(7, 2, _('transcript'), format_meta_bold_left_small)

        # user title
        self.worksheet.write_string(9, 0, '№', format_header_text)
        self.worksheet.write_string(9, 1, _('full name'), format_header_text)
        self.worksheet.write_string(9, 2, _('POSITION'), format_header_text)
        self.worksheet.write_string(9, 3, '', format_header_text)
        count_of_days = len(self.prod_days) + 4
        if not self.on_print:
            # right info
            self.worksheet.set_column(count_of_days, count_of_days, 75 / 6.23820623)
            self.worksheet.set_column(count_of_days + 1, count_of_days + 1, 75 / 6.23820623)
            self.worksheet.set_column(count_of_days + 2, count_of_days + 2, 100 / 6.23820623)
            self.worksheet.set_column(count_of_days + 3, count_of_days + 3, 75 / 6.23820623)
            self.worksheet.set_column(count_of_days + 4, count_of_days + 4, 75 / 6.23820623)
            self.worksheet.set_column(count_of_days + 5, count_of_days + 5, 150 / 6.23820623)
            self.worksheet.write_string(9, count_of_days, _('plan days'), format_header_text)
            self.worksheet.write_string(9, count_of_days + 1, _('plan hours'), format_header_text)
            self.worksheet.write_string(9, count_of_days + 2, _('the rate of hours per month'), format_header_text)
            self.worksheet.write_string(9, count_of_days + 3, _('overtime'), format_header_text)
            self.worksheet.write_string(9, count_of_days + 4, _('date'), format_header_text)
            self.worksheet.write_string(9, count_of_days + 5, _('I have read the work schedule**. I agree to work on public holidays'),
                                        format_header_text)
            self.worksheet.write_string(9, count_of_days + 6, _('H'), format_header_text)
            self.worksheet.write_string(9, count_of_days + 7, _('V'), format_header_text)

    def fill_table(self, workdays, employments, stat, row_s, col_s, stat_type='approved', norm_type='norm_hours', mapping=None):
        """
        одинаковая сортировка у workdays и users должна быть
        :param workdays:
        :param employments:
        :return:
        """

        mapping = mapping or self.WD_TYPE_MAPPING
        cell_format = dict(self.day_type)
        for row_shift, employment in enumerate(employments):
            max_rows = 2
            for day, dt in enumerate(self.prod_days):
                texts = []
                if workdays.get(employment.employee_id, {}).get(dt.dt):
                    wds = workdays.get(employment.employee_id, {}).get(dt.dt)
                    if len(wds) > max_rows:
                        max_rows = len(wds)
                    wd_types = list(set(map(lambda x: x.type_id, wds)))
                    font_color = COLOR_BLACK
                    bg_color = COLOR_WHITE

                    if len(wd_types) == 1:
                        font_color = self.WORKERDAY_TYPE_COLORS[wd_types[0]][0]
                        bg_color = self.WORKERDAY_TYPE_COLORS[wd_types[0]][1]
                    for wd in wds:
                        if not wd.type.is_dayoff:
                            text = '{}-{}'.format(wd.dttm_work_start.time().strftime(QOS_SHORT_TIME_FORMAT),
                                                    wd.dttm_work_end.time().strftime(QOS_SHORT_TIME_FORMAT))
                            if not wd.type_id == WorkerDay.TYPE_WORKDAY:
                                text = mapping[wd.type_id] + text
                        else:
                            text = mapping[wd.type_id]
                        
                        texts.append(text)
                    
                    cell_format.update({
                        'font_color': font_color,
                        'bg_color': bg_color,
                    })

                else:
                    text = ''
                    cell_format.update({
                        'font_color': COLOR_BLACK,
                        'bg_color': COLOR_GREY,
                    })

                self.worksheet.write_string(
                    row_s + row_shift,
                    col_s + day,
                    '\n'.join(texts),
                    self.workbook.add_format(cell_format)
                )
            self.worksheet.set_row(row_s + row_shift, (17.5 if not self.on_print else 10) * max_rows)

            if not self.on_print:

                format_holiday_debt = self.workbook.add_format(fmt(font_size=10, border=1, bg_color='#FEFF99'))

                self.worksheet.write_string(
                    row_s + row_shift, col_s - 1,
                    '',
                    format_holiday_debt
                )
                format_text = self.workbook.add_format(fmt(font_size=12, border=1, bold=True))
                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 1,
                    str(stat.get(employment.employee_id, {}).get('plan', {}).get(stat_type, {}).get('work_days', {}).get('total', 0)),
                    format_text
                )
                
                plan_hours = int(round(stat.get(employment.employee_id, {}).get('plan', {}).get(stat_type, {}).get('work_hours', {}).get('total', 0)))

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 2,
                    str(plan_hours),
                    format_text
                )

                norm_hours = int(round(stat.get(employment.employee_id, {}).get('plan', {}).get(stat_type, {}).get(norm_type, {}).get('curr_month', 0)))

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 3,
                    str(norm_hours),
                    format_text
                )

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 4,
                    str(int(plan_hours - norm_hours)),
                    format_text
                )

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 5,
                    '',
                    format_text
                )

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 6,
                    '',
                    format_text
                )

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 7,
                    str(stat.get(employment.employee_id, {}).get('plan', {}).get(stat_type, {}).get('day_type', {}).get('H', 0)),
                    format_text
                )

                self.worksheet.write_string(
                    row_s + row_shift, col_s + day + 8,
                    str(stat.get(employment.employee_id, {}).get('plan', {}).get(stat_type, {}).get('day_type', {}).get('V', 0)),
                    format_text
                )

    def fill_table2(self, shop, dt_from, workdays):
        def __transpose(__data):
            return list(map(list, zip(*__data)))

        dt_from = datetime(year=dt_from.year, month=dt_from.month, day=1)
        dt_to = dt_from + relativedelta(months=1) - timedelta(days=1)

        self.print_worksheet = self.workbook.add_worksheet(_('On print'))
        format_fio = self.workbook.add_format(fmt2(font_size=10, bold=True, text_wrap=False, align='left', top=2))

        format_common = self.workbook.add_format(fmt2(font_size=7, bold=True))
        format_common_bottom = self.workbook.add_format(fmt2(font_size=7, bold=True, bottom=2))
        format_common_bottom_left = self.workbook.add_format(fmt2(font_size=7, bold=True, bottom=2, left=2))
        format_common_left = self.workbook.add_format(fmt2(font_size=7, bold=True, left=2))

        format_common_top = self.workbook.add_format(fmt2(font_size=7, bold=True, top=2))
        format_common_top_left = self.workbook.add_format(fmt2(font_size=7, bold=True, top=2, left=2))

        format_date = self.workbook.add_format(fmt2(font_size=7, bold=True, num_format='dd/mm', bg_color='#C0C0C0'))
        format_date_bottom = self.workbook.add_format(
            fmt2(font_size=7, bold=True, num_format='dd/mm', bottom=2, bg_color='#C0C0C0'))

        format_time = self.workbook.add_format(fmt2(font_size=7, bold=True, num_format='hh:mm'))
        format_time_bottom = self.workbook.add_format(fmt2(font_size=7, bold=True, num_format='hh:mm', bottom=2))

        weekdays = [Cell(x, format_common_left if x != _('Sun') else format_common_bottom_left) for x in
                    [_('Mon'), _('Tue'), _('Wed'), _('Thu'), _('Fri'), _('Sat'), _('Sun')]]

        data = []
        data_size = {
            'rows': [],
            'cols': []
        }

        prev_user_data = None
        employments = Employment.objects.get_active(
            network_id=shop.network_id,
            dt_from=dt_from,dt_to=dt_to,
            shop_id=shop.id).values_list('employee_id', flat=True)
        employees = Employee.objects.filter(id__in=employments).select_related('user').order_by('id')
        last_worker = len(employees) - 1
        mapping = dict(WorkerDayType.objects.values_list('code', 'excel_load_code'))
        max_rows = [2 for _ in range(7)]
        for i, employee in enumerate(employees):
            worker_days = workdays.get(employee.id, {})
            user_data = [weekdays]
            dt = dt_from - timedelta(days=dt_from.weekday())
            while dt <= dt_to:
                weekdays_dts = []
                cell_data = []
                for xdt in range(int(dt.timestamp()), int((dt + timedelta(days=7)).timestamp()), int(timedelta(days=1).total_seconds())):
                    xdt = datetime.fromtimestamp(xdt)
                    wds = worker_days.get(xdt.date())

                    weekdays_dts.append(Cell(xdt, format_date if xdt.weekday() != 6 else format_date_bottom))
                    texts = []
                    if wds is None:
                        cell_data.append(Cell('', format_common if xdt.weekday() != 6 else format_common_bottom))
                        continue
                    if len(wds) > max_rows[xdt.weekday()]:
                        max_rows[xdt.weekday()] = len(wds)
                    for wd in wds:
                        if not wd.type.is_dayoff:
                            text = '{}-{}'.format(wd.dttm_work_start.time().strftime(QOS_SHORT_TIME_FORMAT),
                                                    wd.dttm_work_end.time().strftime(QOS_SHORT_TIME_FORMAT))
                            if not wd.type_id == WorkerDay.TYPE_WORKDAY:
                                text = mapping[wd.type_id] + text
                        else:
                            text = mapping[wd.type_id]
                        texts.append(text)

                    cell_data.append(Cell('\n'.join(texts),
                                        format_common if xdt.weekday() != 6 else format_common_bottom))

                user_data += [weekdays_dts, cell_data]
                dt += timedelta(days=7)

            user_data = __transpose(user_data)
            user_data = [
                            [
                                Cell('', format_common_top_left),
                                Cell('', format_common_top),
                                Cell('{} {} {}'.format(employee.user.last_name, employee.user.first_name or '',
                                                       employee.user.middle_name or ''), format_fio),
                            ] + [
                                Cell('', format_common_top) for _ in range(len(user_data[0]) - 3)
                            ]
                        ] + user_data

            if i % 2 == 0:
                prev_user_data = user_data

            if (i % 2 == 1) or (last_worker == i):
                data += [row1 + row2 for row1, row2 in zip(prev_user_data, user_data)]

                if len(data_size['cols']) == 0:
                    data_size['cols'] = [3] + [5 if i % 2 == 0 else 10 for i in range(len(prev_user_data[0]) - 1)] + [3] + [5 if i % 2 == 0 else 10 for i in range(
                        len(user_data[0]) - 1)]

                data_size['rows'] += [25] + [max_rows[i] * 10 for i in range(7)]

                max_rows = [2 for _ in range(7)]

                prev_user_data = None

        format_default = self.workbook.add_format(fmt(font_size=10))

        for row_index, row_size in enumerate(data_size['rows']):
            self.print_worksheet.set_row(row_index, row_size)
        for col_index, col_size in enumerate(data_size['cols']):
            self.print_worksheet.set_column(col_index, col_index, col_size)

        for row_index, row in enumerate(data):
            for col_index, cell in enumerate(row):
                if isinstance(cell, Cell):
                    if cell.format is not None:
                        self.print_worksheet.write(row_index, col_index, cell.dttm, cell.format)
                    else:
                        self.print_worksheet.write(row_index, col_index, cell.dttm, format_default)
                else:
                    self.print_worksheet.write(row_index, col_index, cell, format_default)

    def add_sign(self, row, col=3):
        pass
