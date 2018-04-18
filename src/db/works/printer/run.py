import os

import io
import xlsxwriter
from datetime import datetime, timedelta

from src.db.models import WorkerDay, User
from src.util.collection import range_u


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

    for worker in User.objects.filter(shop=shop_id):
        worker_days = {x.dt: x for x in WorkerDay.objects.filter(worker_id=worker.id, dt__gte=dt_from, dt__lte=dt_to)}
        row = [
            Cell('', format_text),
            Cell('{} {} {}'.format(worker.last_name, worker.first_name, worker.middle_name), format_text),
            Cell('кассир-консультант', format_text)
        ] + [
            PrintHelper.get_worker_day_cell(worker_days.get(dttm.date()), format_days) for dttm in __dt_range()
        ]

        data.append(row)
        data_size['rows'] += [40 for i in range(len(row))]


# noinspection PyTypeChecker
def print_to_file(path, shop_id, dt_from, dt_to):
    # df = pandas.DataFrame([
    #     [1010, 2020, 3030, 202220, 1515, 3030, 4545],
    #     [.1, .2, .33, .25, .5, .75, .45],
    # ])

    def __dt_range():
        return range_u(dt_from, dt_to, timedelta(days=1))

    file = io.BytesIO()

    workbook = xlsxwriter.Workbook(filename=file)
    worksheet = workbook.add_worksheet()

    format_default = workbook.add_format(fmt(font_size=10))
    format_header_text = workbook.add_format(fmt(font_size=10, border=2))
    format_header_weekday = workbook.add_format(fmt(font_size=10, border=2))
    format_header_date = workbook.add_format(fmt(font_size=11, border=2, bold=True, num_format='dd/mm'))

    data = [
        ['', '', ''] + [Cell(PrintHelper.get_weekday_name(x), format_header_weekday) for x in __dt_range()],
        [Cell(x, format_header_text) for x in ['№', 'ФИО', 'ДОЛЖНОСТЬ']] + [Cell(x.date(), format_header_date) for x in __dt_range()],
        [],
    ]
    data_size = {
        'rows': [15, 40, 10],
        'cols': [25, 25, 25] + [10 for x in __dt_range()]
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
