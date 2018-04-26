import os

import io
import xlsxwriter
from datetime import datetime, timedelta

from src.db.models import WorkerDay, User
from src.util.collection import range_u, count


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
    def get_worker_day_cell(cls, obj, fmts):
        if obj is None:
            return Cell('', fmts['default'])

        if obj.type == WorkerDay.Type.TYPE_WORKDAY.value:
            return Cell(
                '{}-{}'.format(obj.tm_work_start.strftime('%H:%M'), obj.tm_work_end.strftime('%H:%M')),
                fmts['default']
            )

        if obj.type == WorkerDay.Type.TYPE_HOLIDAY.value:
            return Cell('В', fmts['holiday'])

        if obj.type == WorkerDay.Type.TYPE_VACATION.value:
            return Cell('ОТ', fmts['default'])

        if obj.type == WorkerDay.Type.TYPE_MATERNITY.value:
            return Cell('ОЖ', fmts['default'])


# noinspection PyTypeChecker
def add_workers(workbook, data, data_size, shop_id, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    format_days = {
        'default': workbook.add_format(fmt(font_size=14, border=1)),
        'holiday': workbook.add_format(fmt(font_size=14, border=1, bg_color='#66FF66'))
    }

    format_text = workbook.add_format(fmt(font_size=12, border=1, bold=True))
    format_holiday_debt = workbook.add_format(fmt(font_size=10, border=1, bg_color='#FEFF99'))

    for worker in User.objects.filter(shop=shop_id):
        worker_days = {x.dt: x for x in WorkerDay.objects.filter(worker_id=worker.id, dt__gte=dt_from, dt__lte=dt_to)}
        row = [
            Cell('', format_text),
            Cell('{} {} {}'.format(worker.last_name, worker.first_name, worker.middle_name), format_text),
            Cell('кассир-консультант', format_text),
            Cell('', format_holiday_debt)
        ] + [
            PrintHelper.get_worker_day_cell(worker_days.get(dttm.date()), format_days) for dttm in __dt_range()
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
def fill_sheet_one(workbook, shop_id, dt_from, dt_to):
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

    add_workers(
        workbook=workbook,
        data=data,
        data_size=data_size,
        shop_id=shop_id,
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
    __wt(3, 'b', 'Магазин Алтуфьево', format_meta_bold)
    __wt(4, 'b', 'График работы отдела', format_meta_bold_bottom_2)
    __wt(4, 'c', 'сектор по обслуживанию клиентов', format_meta_bold_bottom_2)
    __wt(4, 'd', '', format_meta_bold_bottom_2)

    __wt(6, 'c', 'Май 2018', format_meta_bold)
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


def create_rect(workbook, shop_id, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

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
    for i, worker in enumerate(User.objects.filter(shop=shop_id)):
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
def fill_sheet_two(workbook, shop_id, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    worksheet = workbook.add_worksheet('На печать')
    format_default = workbook.add_format(fmt(font_size=10))

    data, data_size = create_rect(workbook, shop_id, dt_from, dt_to)

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


# noinspection PyTypeChecker
def print_to_file(path, shop_id, dt_from, dt_to, debug=False):
    file = path if debug else io.BytesIO()

    workbook = xlsxwriter.Workbook(filename=file)
    fill_sheet_one(workbook, shop_id, dt_from, dt_to)
    fill_sheet_two(workbook, shop_id, dt_from, dt_to)
    workbook.close()

    if not debug:
        file.seek(0)

    return file


def run(shop_id, debug=False):
    path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(path, 'test.xlsx')
    if os.path.isfile(file_path):
        os.remove(file_path)

    return print_to_file(
        path=file_path,
        shop_id=shop_id,
        dt_from=datetime(year=2018, month=5, day=1),
        dt_to=datetime(year=2018, month=6, day=1) - timedelta(days=1),
        debug=debug
    )
