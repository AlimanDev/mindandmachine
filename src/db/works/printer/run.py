import os

import io
import xlsxwriter
from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta

from src.db.models import WorkerDay, User, Shop
from src.util.collection import range_u, count
from src.conf.djconfig import QOS_SHORT_TIME_FORMAT

class Cell(object):
    def __init__(self, d, f=None):
        self.d = d
        self.f = f


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


class SheetIndexHelper(object):
    __COLUMNS_MAPPING = None
    __COLUMNS_MAPPING_REVERSE = None

    @staticmethod
    def __create_columns_mapping():
        arr = 'abcdefghijklmnopqrstuvwxyz'
        m = {}
        i = 0

        # for 1-len name
        for c in arr:
            m[c] = i
            i += 1

        # for 2-len name
        for c1 in arr:
            for c2 in arr:
                m[c1 + c2] = i
                i += 1

        return m

    @classmethod
    def __check_columns_mapping(cls):
        if cls.__COLUMNS_MAPPING is None:
            cls.__COLUMNS_MAPPING = cls.__create_columns_mapping()
            cls.__COLUMNS_MAPPING_REVERSE = {v: k for k, v in cls.__COLUMNS_MAPPING.items()}

    @classmethod
    def get_indexes(cls, x, y):
        return cls.get_column(x), cls.get_row(y)

    @classmethod
    def get_column(cls, x):
        cls.__check_columns_mapping()
        return cls.__COLUMNS_MAPPING[x.lower()]

    @classmethod
    def get_row(cls, y):
        return y - 1

    @classmethod
    def reverse_column(cls, x):
        cls.__check_columns_mapping()
        return cls.__COLUMNS_MAPPING_REVERSE[x]

    @classmethod
    def reverse_row(cls, y):
        return y + 1

    @classmethod
    def print_indexes(cls, x, y):
        cls.__check_columns_mapping()
        print('column = {}, row = {}'.format(cls.__COLUMNS_MAPPING_REVERSE[x], y + 1))


class PrintHelper(object):
    @classmethod
    def get_weekday_name(cls, obj):
        if isinstance(obj, datetime):
            wd = obj.weekday()
        else:
            raise Exception('invalid')

        mapping = {
            0: 'Пн',
            1: 'Вт',
            2: 'Ср',
            3: 'Чт',
            4: 'Пт',
            5: 'Сб',
            6: 'Вс'
        }
        return mapping[wd]

    @classmethod
    def common_get_worker_day_cell(cls, obj, fmts):
        if obj is None:
            return Cell('', fmts['default'])

        if obj.type == WorkerDay.Type.TYPE_WORKDAY.value:
            return Cell(
                '{}-{}'.format(obj.tm_work_start.strftime(QOS_SHORT_TIME_FORMAT), obj.tm_work_end.strftime(QOS_SHORT_TIME_FORMAT)),
                fmts['default']
            )

        if obj.type == WorkerDay.Type.TYPE_HOLIDAY.value:
            return Cell('В', fmts['holiday'])

        if obj.type == WorkerDay.Type.TYPE_VACATION.value:
            return Cell('ОТ', fmts['default'])

        if obj.type == WorkerDay.Type.TYPE_MATERNITY.value:
            return Cell('ОЖ', fmts['default'])

        return Cell('', fmts['default'])

    @classmethod
    def depart_get_worker_day_cell(cls, obj, fmts, timetable, timetable_counters):
        def __ret(__value, __fmt='default'):
            return Cell(__value, fmts[__fmt])

        def __tt_add(__key):
            timetable_counters.setdefault(__key, {})
            timetable_counters[__key].setdefault(obj.dt, 0)
            timetable_counters[__key][obj.dt] += 1

        if obj is None:
            return __ret('')

        if obj.type == WorkerDay.Type.TYPE_WORKDAY.value:
            key = '{}-{}'.format(obj.tm_work_start.strftime(QOS_SHORT_TIME_FORMAT), obj.tm_work_end.strftime(QOS_SHORT_TIME_FORMAT))
            value = timetable[key]

            __tt_add(value)
            __tt_add('_work_all')

            return __ret(value)

        if obj.type == WorkerDay.Type.TYPE_HOLIDAY.value:
            __tt_add('_holiday')
            __tt_add('_holiday_and_vacation')

            return __ret('в', 'holiday')

        if obj.type == WorkerDay.Type.TYPE_VACATION.value:
            __tt_add('_vacation')
            __tt_add('_holiday_and_vacation')
            return __ret('от', 'vacation')

        if obj.type == WorkerDay.Type.TYPE_MATERNITY.value:
            return __ret('ож')

        return __ret('')

    @classmethod
    def get_month_name(cls, dt_from):
        return {
            1: 'Январь',
            2: 'Февраль',
            3: 'Март',
            4: 'Апрель',
            5: 'Май',
            6: 'Июнь',
            7: 'Июль',
            8: 'Август',
            9: 'Сентябрь',
            10: 'Октябрь',
            11: 'Ноябрь',
            12: 'Декабрь',
        }.get(dt_from.month, '')


# noinspection PyTypeChecker
def common_add_workers_one(workbook, data, data_size, shop_id, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    format_days = {
        'default': workbook.add_format(fmt(font_size=14, border=1)),
        'holiday': workbook.add_format(fmt(font_size=14, border=1, bg_color='#66FF66'))
    }

    format_text = workbook.add_format(fmt(font_size=12, border=1, bold=True))
    format_holiday_debt = workbook.add_format(fmt(font_size=10, border=1, bg_color='#FEFF99'))

    for worker in User.objects.qos_filter_active(dt_from, dt_to, shop_id=shop_id).order_by('id'):
        worker_days = {x.dt: x for x in WorkerDay.objects.filter(worker_id=worker.id, dt__gte=dt_from, dt__lte=dt_to)}
        row = [
            Cell('', format_text),
            Cell('{} {} {}'.format(worker.last_name, worker.first_name, worker.middle_name), format_text),
            Cell('кассир-консультант', format_text),
            Cell('', format_holiday_debt)
        ] + [
            PrintHelper.common_get_worker_day_cell(worker_days.get(dttm.date()), format_days) for dttm in __dt_range()
        ] + [
            Cell(count(worker_days.values(), lambda x: x.type == WorkerDay.Type.TYPE_WORKDAY.value), format_text),
            Cell('', format_text),
            Cell('', format_text),
            Cell(count(worker_days.values(), lambda x: x.type == WorkerDay.Type.TYPE_HOLIDAY.value), format_text),
            Cell(count(worker_days.values(), lambda x: x.type == WorkerDay.Type.TYPE_VACATION.value), format_text)
        ]

        data.append(row)
        data_size['rows'] += [40 for i in range(len(row))]


# noinspection PyTypeChecker
def common_fill_sheet_one(workbook, shop, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    worksheet = workbook.add_worksheet(name='Расписание на подпись')

    format_default = workbook.add_format(fmt(font_size=10))
    format_header_text = workbook.add_format(fmt(font_size=10, border=2))
    format_header_weekday = workbook.add_format(fmt(font_size=10, border=2))
    format_header_date = workbook.add_format(fmt(font_size=11, border=2, bold=True, num_format='dd/mm'))

    data = [
        [] for i in range(15)
    ] + [
        # weekdays
        ['', '', '', ''] + [Cell(PrintHelper.get_weekday_name(x), format_header_weekday) for x in __dt_range()],

        # main header
        [Cell(x, format_header_text) for x in ['№', 'ФИО', 'ДОЛЖНОСТЬ', 'долг по выходным']] +
        [Cell(x.date(), format_header_date) for x in __dt_range()] +
        [Cell(x, format_header_text) for x in ['плановые дни', 'дата', 'С графиком работы ознакомлен**. На работу в праздничные дни согласен', 'В', 'ОТ']],

        # empty row
        [],
    ]
    data_size = {
        'rows': [15 for i in range(15)] + [15, 40, 10],
        'cols': [25, 30, 25, 20] + [10 for x in __dt_range()] + [15, 15, 25, 10, 10]
    }

    common_add_workers_one(
        workbook=workbook,
        data=data,
        data_size=data_size,
        shop_id=shop.id,
        dt_from=dt_from,
        dt_to=dt_to
    )

    for row_index, row_size in enumerate(data_size['rows']):
        worksheet.set_row(row_index, row_size)
    for col_index, col_size in enumerate(data_size['cols']):
        worksheet.set_column(col_index, col_index, col_size)

    for row_index, row in enumerate(data):
        for col_index, cell in enumerate(row):
            if isinstance(cell, Cell):
                if cell.f is not None:
                    worksheet.write(row_index, col_index, cell.d, cell.f)
                else:
                    worksheet.write(row_index, col_index, cell.d, format_default)
            else:
                worksheet.write(row_index, col_index, cell, format_default)

    format_meta_bold = workbook.add_format(fmt(font_size=11, bold=True, align='left', text_wrap=False))
    format_meta_bold_bottom = workbook.add_format(fmt(font_size=11, bold=True, align='left', text_wrap=False, bottom=1))
    format_meta_bold_bottom_2 = workbook.add_format(fmt(font_size=11, bold=True, align='left', text_wrap=False, bottom=2))
    format_meta_bold_left_small = workbook.add_format(fmt(font_size=9, bold=True, align='left', text_wrap=False))
    format_meta_bold_right_small = workbook.add_format(fmt(font_size=9, bold=True, align='right', text_wrap=False))

    format_meta_workerday_holiday = workbook.add_format(fmt(font_size=11, bold=True, bg_color='#66FF66'))
    format_meta_workerday_z = workbook.add_format(fmt(font_size=11, bold=True, bg_color='#99CCFF'))
    format_meta_common = workbook.add_format(fmt(font_size=9, align='left', text_wrap=False))

    def __wt(__row, __col, __data, __fmt):
        worksheet.write(SheetIndexHelper.get_row(__row), SheetIndexHelper.get_column(__col), __data, __fmt)

    __wt(2, 'b', 'ООО "ЛЕРУА МЕРЛЕН ВОСТОК"', format_meta_bold)
    __wt(3, 'b', 'Магазин {}'.format(shop.super_shop.title), format_meta_bold)
    __wt(4, 'b', 'График работы отдела', format_meta_bold_bottom_2)
    __wt(4, 'c', 'сектор по обслуживанию клиентов', format_meta_bold_bottom_2)
    __wt(4, 'd', '', format_meta_bold_bottom_2)

    __wt(6, 'c', '{} 2018'.format(PrintHelper.get_month_name(dt_from)), format_meta_bold)
    __wt(7, 'b', 'составил:', format_meta_bold_bottom)
    __wt(7, 'c', '', format_meta_bold_bottom)
    __wt(7, 'd', '', format_meta_bold_bottom)
    __wt(8, 'b', 'подпись', format_meta_bold_right_small)
    __wt(8, 'd', 'расшифровка', format_meta_bold_left_small)

    __wt(
        12,
        'b',
        '* включает очередной, учебный и административный отпуск, отпуск по берем. и родам, отпуск по уходу за ребенком до 3-х лет, командировка. В случае отмены или переноса запланированного отсутствия сотрудник работает с с 9:00 до 18:00',
        format_meta_common
    )
    __wt(
        13,
        'b',
        '** в обязательном порядке все сотрудники ознакомлены с Графиком сменности до вступления его в силу за 1 месяц',
        format_meta_common
    )

    __wt(2, 'h', 'условные обозначения', format_meta_bold)
    __wt(4, 'h', 'В', format_meta_workerday_holiday)
    __wt(4, 'i', 'выходой день', format_meta_bold)
    __wt(6, 'h', 'Z*', format_meta_workerday_z)
    __wt(6, 'i', 'запланированное отсутствие', format_meta_bold)

    __wt(1, 'w', 'Согласовано:', format_meta_bold)
    __wt(3, 'w', 'Руководитель сектора по обслуживанию клиентов', format_meta_bold_bottom)
    __wt(3, 'x', '', format_meta_bold_bottom)
    __wt(3, 'y', '', format_meta_bold_bottom)
    __wt(3, 'z', '', format_meta_bold_bottom)
    __wt(3, 'aa', '', format_meta_bold_bottom)
    __wt(4, 'x', 'наименование должности', format_meta_common)

    __wt(6, 'x', '', format_meta_bold_bottom)
    __wt(6, 'y', '', format_meta_bold_bottom)
    __wt(6, 'z', '', format_meta_bold_bottom)
    __wt(6, 'aa', '', format_meta_bold_bottom)
    __wt(6, 'ab', '', format_meta_bold_bottom)
    __wt(6, 'ac', '', format_meta_bold_bottom)
    __wt(6, 'ad', '', format_meta_bold_bottom)

    __wt(7, 'y', 'подпись', format_meta_common)
    __wt(7, 'ac', 'расшифровка', format_meta_common)

    __wt(8, 'x', '', format_meta_bold_bottom)
    __wt(8, 'y', '', format_meta_bold_bottom)
    __wt(8, 'z', '', format_meta_bold_bottom)
    __wt(8, 'aa', '', format_meta_bold_bottom)


def common_add_workers_two(workbook, shop_id, dt_from, dt_to):
    def __transpose(__data):
        return list(map(list, zip(*__data)))

    format_fio = workbook.add_format(fmt2(font_size=10, bold=True, text_wrap=False, align='left', top=2))

    format_common = workbook.add_format(fmt2(font_size=7, bold=True))
    format_common_bottom = workbook.add_format(fmt2(font_size=7, bold=True, bottom=2))
    format_common_bottom_left = workbook.add_format(fmt2(font_size=7, bold=True, bottom=2, left=2))
    format_common_left = workbook.add_format(fmt2(font_size=7, bold=True, left=2))

    format_common_top = workbook.add_format(fmt2(font_size=7, bold=True, top=2))
    format_common_top_left = workbook.add_format(fmt2(font_size=7, bold=True, top=2, left=2))

    format_date = workbook.add_format(fmt2(font_size=7, bold=True, num_format='dd/mm', bg_color='#C0C0C0'))
    format_date_bottom = workbook.add_format(fmt2(font_size=7, bold=True, num_format='dd/mm', bottom=2, bg_color='#C0C0C0'))

    format_time = workbook.add_format(fmt2(font_size=7, bold=True, num_format='hh:mm'))
    format_time_bottom = workbook.add_format(fmt2(font_size=7, bold=True, num_format='hh:mm', bottom=2))

    weekdays = [Cell(x, format_common_left if x != 'Вс' else format_common_bottom_left) for x in ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']]

    data = []
    data_size = {
        'rows': [],
        'cols': []
    }

    prev_user_data = None
    for i, worker in enumerate(User.objects.qos_filter_active(dt_from, dt_to, shop_id=shop_id).order_by('id')):
        worker_days = {x.dt: x for x in WorkerDay.objects.filter(worker_id=worker.id, dt__gte=dt_from, dt__lte=dt_to)}

        user_data = [weekdays]
        dt = dt_from - timedelta(days=dt_from.weekday())
        while dt <= dt_to:
            weekdays_dts = []
            work_begin = []
            work_end = []
            for xdt in range_u(dt, dt + timedelta(days=7), timedelta(days=1), False):
                wd = worker_days.get(xdt.date())

                weekdays_dts.append(Cell(xdt, format_date if xdt.weekday() != 6 else format_date_bottom))
                if wd is None:
                    work_begin.append(Cell('', format_common if xdt.weekday() != 6 else format_common_bottom))
                    work_end.append(Cell('', format_common if xdt.weekday() != 6 else format_common_bottom))
                    continue

                if wd.type == WorkerDay.Type.TYPE_WORKDAY.value:
                    work_begin.append(Cell(wd.tm_work_start, format_time if xdt.weekday() != 6 else format_time_bottom))
                    work_end.append(Cell(wd.tm_work_end, format_time if xdt.weekday() != 6 else format_time_bottom))
                    continue

                mapping = {
                    WorkerDay.Type.TYPE_HOLIDAY.value: 'В',
                    WorkerDay.Type.TYPE_VACATION.value: 'ОТ',
                    WorkerDay.Type.TYPE_MATERNITY.value: 'ОЖ'
                }

                text = mapping.get(wd.type)
                work_begin.append(Cell('' if text is None else text, format_common if xdt.weekday() != 6 else format_common_bottom))
                work_end.append(Cell('' if text is None else text, format_common if xdt.weekday() != 6 else format_common_bottom))

            user_data += [weekdays_dts, work_begin, work_end]
            dt += timedelta(days=7)

        user_data = __transpose(user_data)
        user_data = [
            [
                Cell('', format_common_top_left),
                Cell('', format_common_top),
                Cell('{} {} {}'.format(worker.last_name, worker.first_name, worker.middle_name), format_fio),
            ] + [
                Cell('', format_common_top) for _ in range(len(user_data[0]) - 3)
            ]
        ] + user_data

        if i % 2 == 0:
            prev_user_data = user_data
        else:
            data += [row1 + row2 for row1, row2 in zip(prev_user_data, user_data)]

            if len(data_size['cols']) == 0:
                data_size['cols'] = [3] + [5 for _ in range(len(prev_user_data[0]) - 1)] + [3] + [5 for _ in range(len(user_data[0]) - 1)]

            data_size['rows'] += [25] + [20 for _ in range(7)]

            prev_user_data = None

    return data, data_size


# noinspection PyTypeChecker
def common_fill_sheet_two(workbook, shop, dt_from, dt_to):
    worksheet = workbook.add_worksheet('На печать')
    format_default = workbook.add_format(fmt(font_size=10))

    data, data_size = common_add_workers_two(workbook, shop.id, dt_from, dt_to)

    for row_index, row_size in enumerate(data_size['rows']):
        worksheet.set_row(row_index, row_size)
    for col_index, col_size in enumerate(data_size['cols']):
        worksheet.set_column(col_index, col_index, col_size)

    for row_index, row in enumerate(data):
        for col_index, cell in enumerate(row):
            if isinstance(cell, Cell):
                if cell.f is not None:
                    worksheet.write(row_index, col_index, cell.d, cell.f)
                else:
                    worksheet.write(row_index, col_index, cell.d, format_default)
            else:
                worksheet.write(row_index, col_index, cell, format_default)


# !!!
# noinspection PyTypeChecker
def depart_add_workers_one(workbook, data, data_size, shop_id, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    format_days = {
        'default': workbook.add_format(fmt3(font_size=10, border=1)),
        'holiday': workbook.add_format(fmt3(font_size=10, bg_color='#66FF66', border=1, bottom=2)),
        'vacation': workbook.add_format(fmt3(font_size=10, bg_color='#ccffff', border=1))
    }

    format_text = workbook.add_format(fmt3(font_size=10, border=1))
    format_text_bold = workbook.add_format(fmt3(font_size=10, bold=True, border=1))
    format_text_left = workbook.add_format(fmt3(font_size=9, align='left'))
    format_text_workers = workbook.add_format(fmt3(font_size=11, bold=True, align='left', border=1, right=2))
    format_text_yellow = workbook.add_format(fmt3(font_size=10, border=1, bg_color='#ffff99'))
    format_text_border = workbook.add_format(fmt3(font_size=11, bold=True, align='left', border=1))

    cache_workers = User.objects.qos_filter_active(dt_from, dt_to, shop_id=shop_id).order_by('id')
    cache_worker_days = {}

    timetable_raw = {}
    for worker in cache_workers:
        worker_days = {x.dt: x for x in WorkerDay.objects.filter(worker_id=worker.id, dt__gte=dt_from, dt__lte=dt_to)}
        cache_worker_days[worker.id] = worker_days

        for wd in worker_days.values():
            if wd.type != WorkerDay.Type.TYPE_WORKDAY.value:
                continue
            key = '{}-{}'.format(wd.tm_work_start.strftime(QOS_SHORT_TIME_FORMAT), wd.tm_work_end.strftime(QOS_SHORT_TIME_FORMAT))
            timetable_raw[key] = [wd.tm_work_start, wd.tm_work_end]

    timetable = {}
    counter = 1
    for x in sorted([[tt_key, tt_value[0], tt_value[1]] for tt_key, tt_value in timetable_raw.items()], key=lambda x: x[1]):
        timetable[x[0]] = counter
        counter += 1

    timetable_counters = {
        '_holiday': {},
        '_vacation': {},
        '_holiday_and_vacation': {},
        '_work_all': {},
    }
    for worker in cache_workers:
        worker_days = cache_worker_days[worker.id]
        row = [
            Cell('', format_text_border),
            Cell('', format_text_border),
            Cell('', format_text_border),
            Cell('{} {} {}'.format(worker.last_name, worker.first_name, worker.middle_name), format_text_workers),
        ] + [
            PrintHelper.depart_get_worker_day_cell(worker_days.get(dttm.date()), format_days, timetable, timetable_counters) for dttm in __dt_range()
        ] + [
            Cell(count(worker_days.values(), lambda x: x.type == WorkerDay.Type.TYPE_HOLIDAY.value), format_text),  # выходных
            Cell(count(worker_days.values(), lambda x: x.type == WorkerDay.Type.TYPE_WORKDAY.value), format_text_bold),  # плановых
            Cell('', format_text_yellow),
            Cell('', format_text),
            Cell('', format_text)
        ]

        data.append(row)
        data_size['rows'] += [15]

    data += [
        [],  # пустая строка
        [],  # информация
        [],  # начало-конец
    ]
    data_size['rows'] += [30, 15, 15, 30]
    row_timetable_header = len(data) - 2

    return {
        'row_timetable_header': row_timetable_header,
        'timetable': timetable,
        'timetable_counters': timetable_counters
    }


# !!!
# noinspection PyTypeChecker
def depart_fill_sheet_one(workbook, shop, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    def __dt_range_len():
        return len([1 for _ in __dt_range()])

    worksheet = workbook.add_worksheet(name='Расписание на подпись')
    # worksheet.hide_gridlines(2)

    format_default = workbook.add_format(fmt3(font_size=9))
    format_header_text = workbook.add_format(fmt3(font_size=8, border=1))
    format_header_text_bold = workbook.add_format(fmt3(font_size=8, bold=True))
    format_header_weekday = workbook.add_format(fmt3(font_size=9))
    format_header_date = workbook.add_format(fmt3(font_size=8, bold=True, num_format='dd', border=1))

    data = [
        [] for i in range(9)
    ] + [
        # main header
        [Cell(x, format_header_text) for x in ['№ п/п', 'Таб №', 'должн', 'Фамилия Имя Отчество']] +
        [Cell(x.date(), format_header_date) for x in __dt_range()] +
        # [Cell(PrintHelper.get_weekday_name(x), format_header_text_bold) for x in __dt_range()] +
        [Cell(x, format_header_text) for x in ['вых дни', 'раб дни', 'вых дни', 'дата', 'подпись']]
    ]
    data_size = {
        'rows': [14, 20, 14, 20, 14, 35, 14, 14, 20, 40],
        'cols': [5, 10, 5, 40] + [2 for x in __dt_range()] + [3, 3, 4, 5, 5]
    }

    extra = depart_add_workers_one(
        workbook=workbook,
        data=data,
        data_size=data_size,
        shop_id=shop.id,
        dt_from=dt_from,
        dt_to=dt_to
    )

    for row_index, row_size in enumerate(data_size['rows']):
        worksheet.set_row(row_index, row_size)
    for col_index, col_size in enumerate(data_size['cols']):
        worksheet.set_column(col_index, col_index, col_size)

    for row_index, row in enumerate(data):
        for col_index, cell in enumerate(row):
            if isinstance(cell, Cell):
                if cell.f is not None:
                    worksheet.write(row_index, col_index, cell.d, cell.f)
                else:
                    worksheet.write(row_index, col_index, cell.d, format_default)
            else:
                worksheet.write(row_index, col_index, cell, format_default)

    format_meta_title = workbook.add_format(fmt3(font_size=8, text_wrap=False))
    format_meta_title_border = workbook.add_format(fmt3(font_size=8, border=1))
    format_meta_title_border_10_yellow = workbook.add_format(fmt3(font_size=10, border=1, bg_color='#ffc000'))
    format_meta_title_border_10_right_yellow = workbook.add_format(fmt3(font_size=10, border=1, bg_color='#ffc000', right=2))
    format_meta_title_border_bottom = workbook.add_format(fmt3(font_size=8, text_wrap=False, bottom=1))
    format_meta_main_title = workbook.add_format(fmt3(font_size=28, bold=True, text_wrap=False, align='center', bottom=1))
    format_meta_title_10 = workbook.add_format(fmt3(font_size=10, text_wrap=False))
    format_meta_title_bold_12_left = workbook.add_format(fmt3(font_size=12, bold=True, text_wrap=False, align='left'))
    format_meta_title_bold_14_left = workbook.add_format(fmt3(font_size=14, bold=True, text_wrap=False, align='left'))
    format_meta_title_bold_10_right_bottom = workbook.add_format(fmt3(font_size=10, bold=True, text_wrap=False, align='right', valign='bottom'))
    format_meta_title_bold_10_bold_border = workbook.add_format(fmt3(font_size=10, text_wrap=False, align='right', border=2))
    format_meta_title_bold_14_border = workbook.add_format(fmt3(font_size=14, bold=True, text_wrap=False, align='center', border=1))
    format_meta_title_bold = workbook.add_format(fmt3(font_size=8, bold=True, text_wrap=False))
    format_meta_text_cursive_7 = workbook.add_format(fmt3(font_size=7, text_wrap=False))
    format_meta_title_16 = workbook.add_format(fmt3(font_size=16, text_wrap=False, right=1))
    format_meta_text_border_10 = workbook.add_format(fmt3(font_size=10, text_wrap=False, border=1))
    format_meta_text_border_10_right = workbook.add_format(fmt3(font_size=10, text_wrap=False, border=1, right=2))

    format_meta_title_border_right = workbook.add_format(fmt3(font_size=8, border=1, right=2))
    format_meta_title_left = workbook.add_format(fmt3(font_size=8, text_wrap=False, align='left'))
    format_meta_title_bold_left = workbook.add_format(fmt3(font_size=8, bold=True, text_wrap=False, align='left'))
    format_meta_title_right = workbook.add_format(fmt3(font_size=8, text_wrap=False, align='right'))
    format_meta_title_bold_right = workbook.add_format(fmt3(font_size=8, bold=True, text_wrap=False, align='right'))

    def __wt(__row, __col, __data, __fmt):
        worksheet.write(SheetIndexHelper.get_row(__row), SheetIndexHelper.get_column(__col), __data, __fmt)

    def __wt_f(__row, __col, __data, __fmt):
        worksheet.write_formula(SheetIndexHelper.get_row(__row), SheetIndexHelper.get_column(__col), __data, __fmt)

    __wt(2, 'g', 'ГРАФИК РАБОТЫ', format_meta_title_bold_14_left)
    worksheet.merge_range('AH3:AM3', 'Наименование должности', format_meta_title)
    worksheet.merge_range('AH5:AM5', 'Подпись, расшифровка', format_meta_title)
    __wt(6, 'd', 'Подразделение:', format_meta_title_bold_10_right_bottom)

    worksheet.merge_range('AH1:AM1', 'УТВЕРЖДАЮ', format_meta_title_bold_12_left)
    worksheet.merge_range('E6:AB6', '{}'.format(shop.title), format_meta_main_title)
    worksheet.merge_range('AH2:AM2', '', format_meta_title_border_bottom)
    worksheet.merge_range('AH4:AM4', '', format_meta_title_border_bottom)
    worksheet.merge_range('AH7:AM7', '\"____\" __________ 2018 г.', format_meta_title)

    last_dt_column_index = SheetIndexHelper.get_column('e') + __dt_range_len() - 1

    worksheet.merge_range(
        'E9:{}9'.format(SheetIndexHelper.reverse_column(last_dt_column_index).upper()),
        '{} 2018'.format(PrintHelper.get_month_name(dt_from).upper()),
        format_meta_title_bold_14_border
    )

    worksheet.merge_range(
        '{}9:{}9'.format(SheetIndexHelper.reverse_column(last_dt_column_index + 1), SheetIndexHelper.reverse_column(last_dt_column_index + 2)).upper(),
        'Запланировано',
        format_header_text
    )

    __wt(9, SheetIndexHelper.reverse_column(last_dt_column_index + 3), 'Отклонения', format_header_text)

    worksheet.merge_range(
        '{}9:{}9'.format(SheetIndexHelper.reverse_column(last_dt_column_index + 4), SheetIndexHelper.reverse_column(last_dt_column_index + 5)).upper(),
        'С графиком ознакомлен',
        format_header_text
    )

    # __wt(2, 'x', 'ООО "ЛЕРУА МЕРЛЕН ВОСТОК"', format_meta_title_bold)
    # __wt(3, 'x', '(наименование организации)', format_meta_title)
    # __wt(4, 'x', 'МАГАЗИН {}'.format(shop.super_shop.title.upper()), format_meta_title_bold)
    # __wt(5, 'x', '(наименование структурного подразделения)', format_meta_title)
    #
    # __wt(6, 'b', 'собрание отдела 19.05.2018', format_meta_title)
    #
    # __wt(7, 't', 'ГРАФИК СМЕННОСТИ', format_meta_title_bold)
    # __wt(8, 's', 'ОТДЕЛА', format_meta_title_bold)
    #
    # __wt(6, 'ad', '№ ОТДЕЛА', format_meta_title)
    #
    # try:
    #     s = int(shop.hidden_title.replace('d', ''))
    #     __wt(7, 'ad', '{}'.format(s), format_meta_title_bold)
    # except:
    #     pass
    #
    # __wt(9, 'ab', 'УТВЕРЖДАЮ', format_meta_title_bold_left)
    # __wt(10, 'ab', 'личная подпись', format_meta_title_left)
    # __wt(11, 'ab', 'дата', format_meta_title_bold_left)
    #
    # __wt(7, 'AK', 'Май', format_meta_title_bold_12)

    row_timetable_header = extra['row_timetable_header']
    timetable = {v: k for k, v in extra['timetable'].items()}

    def __tt_counters(__key, __dt):
        return extra['timetable_counters'][__key].get(__dt.date(), 0)

    __wt(row_timetable_header, 'd', 'Составил:', format_meta_title_bold_10_bold_border)
    worksheet.merge_range('E{0}:J{0}'.format(row_timetable_header), '', format_meta_title_border_bottom)
    worksheet.merge_range('N{0}:Q{0}'.format(row_timetable_header), '', format_meta_title_border_bottom)
    worksheet.merge_range('T{0}:Y{0}'.format(row_timetable_header), '', format_meta_title_border_bottom)
    worksheet.merge_range('AC{0}:AF{0}'.format(row_timetable_header), '', format_meta_title_border_bottom)

    worksheet.merge_range('E{0}:J{0}'.format(row_timetable_header + 1), 'Наименование должности', format_meta_text_cursive_7)
    worksheet.merge_range('N{0}:Q{0}'.format(row_timetable_header + 1), 'Подпись', format_meta_text_cursive_7)
    worksheet.merge_range('T{0}:Y{0}'.format(row_timetable_header + 1), 'Расшифровка подписи', format_meta_text_cursive_7)
    worksheet.merge_range('AC{0}:AF{0}'.format(row_timetable_header + 1), 'Дата', format_meta_text_cursive_7)

    __wt(row_timetable_header + 2, 'b', 'СПРАВОЧНО:', format_meta_title_bold)

    __wt(row_timetable_header + 3, 'b', 'Обозначение', format_meta_title_border)
    __wt(row_timetable_header + 3, 'c', '', format_meta_title_border)
    __wt(row_timetable_header + 3, 'd', 'Время начала и окончания смен (с учетом перерыва продолжительностью 1 час)', format_meta_title_border)

    col_index = SheetIndexHelper.get_column('e')
    for x in __dt_range():
        __wt(row_timetable_header + 3, SheetIndexHelper.reverse_column(col_index), x.date(), format_header_date)
        col_index += 1

    i = 0
    for tt_value in sorted(timetable):
        tt_key = timetable[tt_value]

        tt_begin, tt_end = tt_key.split('-')
        row_index = row_timetable_header + 4 + i
        __wt(row_index, 'b', tt_value, format_meta_text_border_10)
        __wt(row_index, 'c', '', format_meta_text_border_10)
        __wt(row_index, 'd', 'с {} до {}'.format(tt_begin, tt_end), format_meta_text_border_10_right)

        col_index = SheetIndexHelper.get_column('e')
        for x in __dt_range():
            __wt(
                row_index,
                SheetIndexHelper.reverse_column(col_index),
                __tt_counters(tt_value, x),
                format_meta_text_border_10
            )
            col_index += 1

        i += 1

    for tt_key, tt_value_raw in {'в': ('выходной', '_holiday'), 'от': ('отпуск', '_vacation')}.items():
        tt_value = tt_value_raw[0]

        row_index = row_timetable_header + 4 + i
        __wt(row_index, 'b', tt_key, format_meta_text_border_10)
        __wt(row_index, 'c', '', format_meta_text_border_10)
        __wt(row_index, 'd', tt_value, format_meta_text_border_10_right)

        col_index = SheetIndexHelper.get_column('e')
        for x in __dt_range():
            __wt(
                row_index,
                SheetIndexHelper.reverse_column(col_index),
                __tt_counters(tt_value_raw[1], x),
                format_meta_text_border_10
            )
            col_index += 1

        i += 1

    row_index = row_timetable_header + 4 + i

    worksheet.merge_range('B{0}:D{0}'.format(row_index), 'всего вых и отп', format_meta_text_border_10_right)

    col_index = SheetIndexHelper.get_column('e')
    for x in __dt_range():
        __wt(
            row_index,
            SheetIndexHelper.reverse_column(col_index),
            __tt_counters('_holiday_and_vacation', x),
            format_meta_text_border_10
        )
        col_index += 1

    worksheet.merge_range('B{0}:D{0}'.format(row_index + 1), 'всего раб', format_meta_title_border_10_right_yellow)

    col_index = SheetIndexHelper.get_column('e')
    for x in __dt_range():
        __wt(
            row_index + 1,
            SheetIndexHelper.reverse_column(col_index),
            __tt_counters('_work_all', x),
            format_meta_title_border_10_yellow
        )
        col_index += 1

    worksheet.merge_range('B{0}:D{0}'.format(row_index + 2), 'СОБРАНИЕ ОТДЕЛА СОСТОИТСЯ:', format_meta_title_16)
    __wt(row_index + 4, 'd', 'РАСПИСАНИЕ ПЕРЕРЫВОВ', format_meta_title_10)
    __wt(row_index + 5, 'd', 'Смена', format_meta_title_border)
    worksheet.merge_range('E{0}:H{0}'.format(row_index + 5), '1 перерыв', format_meta_title_border)
    worksheet.merge_range('I{0}:L{0}'.format(row_index + 5), '2 перерыв', format_meta_title_border)
    worksheet.merge_range('M{0}:P{0}'.format(row_index + 5), '3 перерыв', format_meta_title_border)

    i = 0
    for tt_value in sorted(timetable):
        __wt(row_index + 6 + i, 'd', tt_value, format_meta_title_border)
        worksheet.merge_range('E{0}:H{0}'.format(row_index + 6 + i), '', format_meta_title_border)
        worksheet.merge_range('I{0}:L{0}'.format(row_index + 6 + i), '', format_meta_title_border)
        worksheet.merge_range('M{0}:P{0}'.format(row_index + 6 + i), '', format_meta_title_border)

        i += 1

    # __wt(row_timetable_header + 1, 'J', 'с', format_meta_title)
    # __wt(row_timetable_header + 1, 'L', 'по', format_meta_title)
    # __wt(row_timetable_header + 1, 'O', 'длительность', format_meta_title)
    #
    # __wt(row_timetable_header + 1, 'r', 'с', format_meta_title)
    # __wt(row_timetable_header + 1, 's', 'по', format_meta_title)
    # __wt(row_timetable_header + 1, 'v', 'длительность', format_meta_title)

    # i = 0
    # for tt_value in sorted(timetable):
    #     tt_key = timetable[tt_value]
    #
    #     tt_begin, tt_end = tt_key.split('-')
    #     row_index = row_timetable_header + 4 + i
    #     __wt(row_index, 'b', 'Смена № {}'.format(tt_value), format_meta_title_bold_right)
    #
    #     __wt(row_index, 'd', tt_begin, format_meta_title_bold)
    #     __wt(row_index, 'g', tt_end, format_meta_title_bold)
    #
    #     i += 1

    # __wt(row_timetable_header + 2 + i, 'u', 'общая продолжительность перерывов в течение рабочей смены - 1 час', format_meta_title_bold)
    # __wt(
    #     row_timetable_header + 2 + i + 1,
    #     'u',
    #     'Запрещено меняться сменами, выходными днями во избежание нарушения трудового распорядка. В крайних случаях по согласованию с РС и письменному заявлению.',
    #     format_meta_title_bold
    # )


# noinspection PyTypeChecker
def print_to_file(file, shop_id, dt_from, dt_to):
    shop = Shop.objects.get(id=shop_id)

    workbook = xlsxwriter.Workbook(filename=file)

    if shop.full_interface:
        common_fill_sheet_one(workbook, shop, dt_from, dt_to)
        common_fill_sheet_two(workbook, shop, dt_from, dt_to)
    else:
        depart_fill_sheet_one(workbook, shop, dt_from, dt_to)

    workbook.close()

    return file


def run(shop_id, dt_from, debug=False):
    dt_from = datetime(year=dt_from.year, month=dt_from.month, day=1)
    dt_to = dt_from + relativedelta(months=1) - timedelta(days=1)

    if not debug:
        file = io.BytesIO()
    else:
        path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(path, 'test.xlsx')
        if os.path.isfile(file_path):
            os.remove(file_path)

        file = file_path

    result = print_to_file(
        file=file,
        shop_id=shop_id,
        dt_from=dt_from,
        dt_to=dt_to
    )

    if not debug:
        result.seek(0)

    return result
