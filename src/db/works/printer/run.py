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
def print_to_file(path, shop_id, dt_from, dt_to):
    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    file = io.BytesIO()
    # file = path

    workbook = xlsxwriter.Workbook(filename=file)
    worksheet = workbook.add_worksheet()

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

    workbook.close()
    file.seek(0)
    return file


def run(shop_id):
    path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(path, 'test.xlsx')
    if os.path.isfile(file_path):
        os.remove(file_path)

    return print_to_file(
        path=file_path,
        shop_id=shop_id,
        dt_from=datetime(year=2018, month=5, day=1),
        dt_to=datetime(year=2018, month=6, day=1) - timedelta(days=1)
    )
