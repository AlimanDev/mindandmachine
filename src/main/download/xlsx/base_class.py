import datetime
from src.db.models import ProductionDay
from .colors import *


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

    def __init__(self, workbook, shop, dt, worksheet=None, prod_days=None):
        self.workbook = workbook

        self.worksheet = None
        if worksheet:
            self.worksheet = worksheet

        # fucking formatting

        self.default_text = workbook.add_format({
            'font_size': 10,
            'font_name': 'Arial',
        })

        self.shop = shop
        self.super_shop = shop.super_shop
        self.month = datetime.date(dt.year, dt.month, 1)
        self.prod_days = prod_days

        if prod_days is None:
            self.prod_days = list(ProductionDay.objects.filter(
                dt__year=self.month.year,
                dt__month=self.month.month
            ).order_by('dt'))

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
        weekday_translation = [
            'Понедельник',
            'Вторник',
            'Среда',
            'Четверг',
            'Пятница',
            'Суббота',
            'Воскресенье'
        ]

        i = 0
        for item in self.prod_days:
            color = COLOR_WHITE
            if item.type == 'H':
                color = COLOR_GREEN
            if item.type == 'S':
                color = COLOR_ORANGE
            text_type = self.workbook.add_format({
                'font_size': 11,
                'font_name': 'Arial',
                'bold': True,
                'align': 'center',
                'font_color': COLOR_BLACK,
                'border': 1,
                'bg_color': color
            })

            if format == '%w':
                self.worksheet.write_string(row, col + i,
                                            '{}'.format(weekday_translation[int(item.dt.strftime(format))]), text_type)
            else:
                self.worksheet.write_string(row, col + i, '{}'.format(item.dt.strftime(format)), text_type)
            i += 1

        while i < 31:
            text_type = self.workbook.add_format({
                'border': 1,
                'bg_color': COLOR_GREY
            })
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
