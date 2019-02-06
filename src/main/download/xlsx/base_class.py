import datetime
from src.db.models import ProductionDay, ProductionMonth
from .colors import *
from src.util.models_converter import BaseConverter

class Xlsx_base:
    MONTH_NAMES = {
        1: 'Январь',
        2: 'Февраль',
        3: 'Март',
        4: 'Апрель',
        5: 'Май',
        6: 'Июнь',
        7: 'Июль',
        8: 'Август',
        9: 'Сентбярь',
        10: 'Октябрь',
        11: 'Ноябрь',
        12: 'Декабрь',
    }

    WEEKDAY_TRANSLATION = [
        'вс',
        'пн',
        'вт',
        'ср',
        'чт',
        'пт',
        'сб',
    ]

    def __init__(self, workbook, shop, dt, worksheet=None, prod_days=None):
        self.workbook = workbook

        self.worksheet = None
        if worksheet:
            self.worksheet = worksheet

        # fucking formatting

        self.default_text_settings = {
            'font_size': 10,
            'font_name': 'Arial',
            'align': 'center',
            'bold': True,
        }

        self.shop = shop
        self.super_shop = shop.super_shop
        self.month = datetime.date(dt.year, dt.month, 1)
        self.prod_days = prod_days

        if prod_days is None:
            self.prod_days = list(ProductionDay.objects.filter(
                dt__year=self.month.year,
                dt__month=self.month.month
            ).order_by('dt'))

        self.prod_month = ProductionMonth.objects.filter(
            dt_first__month=self.month.month,
            dt_first__year=self.month.year
        ).first()

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
            'font_size': 11,
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'font_color': COLOR_BLACK,
            'border': 1,
            'bg_color': '',
        }

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
            else:
                cell_str = item.dt.strftime(format)
                cell_str = int(cell_str) if xlsx_format==int else cell_str
                writer(row, col + i, cell_str, text_type)
            i += 1

        text_type = self.workbook.add_format({
            'border': 1,
            'bg_color': COLOR_GREY
        })
        while i < 31:
            self.worksheet.write_string(row, col + i, '', text_type)
            i += 1

    def construnts_users_info(self, users, row, col, ordered_columns):
        """
        Записывает в столбик информацию по сотрудникам начиная с row строки в колонки [col, col + len(ordered_columns)].
        В ordered_columns указаны какие поля в каком порядке указывать.

        :param users: queryset
        :param row: int
        :param col: int
        :param ordered_columns: list из 'code', 'fio', 'position', 'hired'
        :return:
        """

        format_s = dict(self.default_text_settings)
        format_s['border'] = 1
        text_format = self.workbook.add_format(format_s)
        format_s['num_format'] = 'dd.mm.yyyy'
        date_format = self.workbook.add_format(format_s)

        user_elem_dict = {
            'code': (lambda u: u.tabel_code, text_format, self.worksheet.write_string),
            'fio': (lambda u: '{} {} {}'.format(u.last_name, u.first_name, u.middle_name), text_format,
                    self.worksheet.write_string),
            'position': (lambda u: u.position.title if u.position else 'Кассир-консультант', text_format, self.worksheet.write_string),
            'hired': (lambda u: BaseConverter.convert_date(u.dt_hired), date_format, self.worksheet.write_datetime),
        }

        for it, user in enumerate(list(users)):
            for col_shift, elem in enumerate(ordered_columns):
                lambda_f, data_format, writer = user_elem_dict[elem]
                try:
                    writer(
                        row + it,
                        col + col_shift,
                        lambda_f(user) or '',
                        data_format
                    )
                except TypeError:
                    self.worksheet.write_string(row + it, col + col_shift, '', text_format)


