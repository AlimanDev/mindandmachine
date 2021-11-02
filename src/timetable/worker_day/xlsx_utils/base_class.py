import datetime

from django.conf import settings
from django.db.models import Case, When, Sum, Value, IntegerField

from src.base.models import ProductionDay
from src.timetable.worker_day.xlsx_utils.colors import *
from src.util.models_converter import Converter


class Xlsx_base:
    WEEKDAY_TRANSLATION = [
        'вс',
        'пн',
        'вт',
        'ср',
        'чт',
        'пт',
        'сб',
    ]

    def __init__(self, workbook, shop, dt, worksheet=None, prod_days=None, on_print=False):
        self.workbook = workbook
        self.on_print = on_print

        self.worksheet = None
        if worksheet:
            self.worksheet = worksheet

        self.default_text_settings = {
            'font_size': self._font_size(10, 8),
            'font_name': 'Arial',
            'align': 'center',
            'valign': 'vcenter',
            'bold': True,
        }

        self.shop = shop
        self.dt = dt
        self.month = datetime.date(dt.year, dt.month, 1)
        self.prod_days = prod_days

        if prod_days is None:
            self.prod_days = list(
                ProductionDay.get_prod_days_for_region(
                    self.shop.region_id,
                    dt__year=self.month.year,
                    dt__month=self.month.month,
                ).order_by('dt')
            )
        self.prod_month = ProductionDay.get_prod_days_for_region(
            self.shop.region_id,
            dt__year=self.month.year,
            dt__month=self.month.month,
            type__in=ProductionDay.WORK_TYPES,
        ).annotate(
            work_hours=Case(
                When(type=ProductionDay.TYPE_WORK, then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_WORK])),
                When(type=ProductionDay.TYPE_SHORT_WORK, then=Value(ProductionDay.WORK_NORM_HOURS[ProductionDay.TYPE_SHORT_WORK])),
            )
        ).aggregate(
            norm_work_hours=Sum('work_hours', output_field=IntegerField())
        )

    def _font_size(self, font_size, on_print_font_size=None):
        if self.on_print:
            return on_print_font_size or int(font_size / 2) + 4
        return font_size

    def _column_width(self, column_width, on_print_column_width=None):
        if self.on_print:
            return on_print_column_width or int(column_width / 2)
        return column_width

    def _row_height(self, row_height, on_print_row_height=None):
        if self.on_print:
            return on_print_row_height or int(row_height / 2)
        return row_height

    def construct_dates(self, format, row, col, xlsx_format=str):
        """
        Записывает даты в указанном в format типе в строку под номером row, начиная с col колонки в self.worksheet. Ячейки надо
        подсвечивать в зависимости от дня в self.prod_days. Всегда заполняет 31 день, если дней меньше, то серым цветом.
        Если формат число или дата, то указать формат ячеек в xlsx_format
        :param format:
        :param row:
        :param col:
        :param xlsx_format:
        :return: None
        """

        text_dict = {
            'font_size': self._font_size(11, 8),
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'valign': 'vcenter',
            'font_color': COLOR_BLACK,
            'border': 1,
            'bg_color': '',
        }
        
        if format == '%w':
            text_dict['font_size'] = self._font_size(11, 11)

        if (xlsx_format == str) :
            writer = self.worksheet.write_string
        elif xlsx_format == int:
            writer = self.worksheet.write_number
        elif type(xlsx_format) == str:
            writer = self.worksheet.write_datetime
            text_dict['num_format'] = xlsx_format
        else:
            # todo: log error
            writer = self.worksheet.write_string

        i = 0
        for item in self.prod_days:
            text_dict['bg_color'] = COLOR_WHITE
            if item.type == 'H':
                text_dict['bg_color'] = COLOR_GREEN
            if item.type == 'S':
                text_dict['bg_color'] = COLOR_ORANGE

            text_type = self.workbook.add_format(text_dict)
            if format == '%w':
                self.worksheet.write_string(row, col + i,
                                            self.WEEKDAY_TRANSLATION[int(item.dt.strftime(format))], text_type)
                self.worksheet.set_column(col + i, col + i, self._column_width(16, 4))
            else:
                cell_str = item.dt.strftime(format)
                cell_str = int(cell_str) if xlsx_format==int else cell_str
                writer(row, col + i, cell_str, text_type)
            i += 1

        text_type = self.workbook.add_format({
            'border': 1,
            'bg_color': COLOR_GREY
        })
        # while i < 31:
        #     self.worksheet.write_string(row, col + i, '', text_type)
        #     i += 1

    def construnts_users_info(self, employments, row, col, ordered_columns, extra_row=False):
        """
        Записывает в столбик информацию по сотрудникам начиная с row строки в колонки [col, col + len(ordered_columns)].
        В ordered_columns указаны какие поля в каком порядке указывать.
        :param employments: queryset
        :param row: int
        :param col: int
        :param ordered_columns: list из 'code', 'fio', 'position', 'hired'
        :return:
        """

        format_s = dict(self.default_text_settings)
        format_s['border'] = 1
        format_s['text_wrap'] = True
        format_s['bold'] = False
        text_format = self.workbook.add_format(format_s)
        format_s['bold'] = True
        bold_text_format = self.workbook.add_format(format_s)
        format_s['num_format'] = 'dd.mm.yyyy'
        date_format = self.workbook.add_format(format_s)

        col_func_dict = {
            'code': (settings.DOWNLOAD_TIMETABLE_GET_CODE_FUNC, bold_text_format, self.worksheet.write_string),
            'fio': (lambda e: '{} {} {}'.format(e.employee.user.last_name, e.employee.user.first_name, e.employee.user.middle_name), text_format,
                    self.worksheet.write_string),
            'position': (lambda e: e.position.name if e.position else 'Не указано', text_format, self.worksheet.write_string),
            'hired': (lambda e: Converter.convert_date(e.dt_hired), date_format, self.worksheet.write_datetime),
        }

        for it, employment in enumerate(list(employments)):
            for col_shift, col_name in enumerate(ordered_columns):
                lambda_f, data_format, writer = col_func_dict[col_name]
                try:
                    if extra_row:
                        shift = 2
                        self.worksheet.merge_range(
                            row + it * shift,
                            col + col_shift,
                            row + it * shift + 1,
                            col + col_shift,
                            lambda_f(employment) or '',
                            data_format
                        )
                    else:
                        self.worksheet.write(
                            row + it,
                            col + col_shift,
                            lambda_f(employment) or '',
                            data_format
                        )

                except TypeError:
                    self.worksheet.write_string(row + it, col + col_shift, '', text_format)
