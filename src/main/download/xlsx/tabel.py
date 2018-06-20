from .base_class import Xlsx_base
from src.db.models import (
    ProductionDay,
    WorkerDay
)
from .colors import *

class Tabel_xlsx(Xlsx_base):
    # (font; background)
    WORKERDAY_TYPE_COLORS = {
        WorkerDay.Type.TYPE_WORKDAY.value: (COLOR_BLACK, COLOR_WHITE),
        WorkerDay.Type.TYPE_BUSINESS_TRIP.value: (COLOR_RED, COLOR_WHITE),
        WorkerDay.Type.TYPE_HOLIDAY.value: (COLOR_BLACK, COLOR_GREEN),
        WorkerDay.Type.TYPE_HOLIDAY_WORK.value: (COLOR_BLACK, COLOR_GREEN),
        WorkerDay.Type.TYPE_ABSENSE.value: (COLOR_BLACK, COLOR_YELLOW_2),
        WorkerDay.Type.TYPE_REAL_ABSENCE.value: (COLOR_BLACK, COLOR_RED),
        WorkerDay.Type.TYPE_SICK.value: (COLOR_BLACK, COLOR_1),
        WorkerDay.Type.TYPE_VACATION.value: (COLOR_BLACK, COLOR_BLUE),
        WorkerDay.Type.TYPE_EXTRA_VACATION.value: (COLOR_RED, COLOR_BLUE),
        WorkerDay.Type.TYPE_TRAIN_VACATION.value: (COLOR_BLACK, COLOR_DARK_BLUE),
        WorkerDay.Type.TYPE_SELF_VACATION.value: (COLOR_BLACK, COLOR_BLUE2),
        WorkerDay.Type.TYPE_SELF_VACATION_TRUE.value: (COLOR_BLACK, COLOR_LITE_GREEN),
        WorkerDay.Type.TYPE_GOVERNMENT.value: (COLOR_BLACK, COLOR_PINK3),
        WorkerDay.Type.TYPE_MATERNITY.value: (COLOR_BLACK, COLOR_GREEN2),

        'night_work': (COLOR_BLACK, COLOR_PINK2),

    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def format_cells(self, users_len):
        def set_rows(row1, row2, heigth):
            for row in range(row1, row2 + 1):
                self.worksheet.set_row(row, heigth)

        normalized = 6.23820623
        self.worksheet.set_column(0, 0, 80 / normalized)
        self.worksheet.set_column(1, 1, 200 / normalized)
        self.worksheet.set_column(2, 2, 160 / normalized)
        self.worksheet.set_column(3, 3, 100 / normalized)
        self.worksheet.set_column(4, 34, 40 / normalized)
        self.worksheet.set_column(35, 35, 50 / normalized)
        self.worksheet.set_column(36, 56, 32 / normalized)
        self.worksheet.set_column(57, 599, 90 / normalized)

        normalized_row = 1
        set_rows(0, 10, 21 / normalized_row)
        set_rows(11, 11, 30 / normalized_row)
        set_rows(12, 12, 35 / normalized_row)
        set_rows(13, 14, 25 / normalized_row)
        set_rows(15, 15, 40 / normalized_row)
        set_rows(16, 16 + users_len, 20 / normalized_row)


    def add_main_info(self):
        # top left info
        text_top = self.workbook.add_format({
            'font_size': 11,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
        })
        text_top_red = self.workbook.add_format({
            'font_size': 11,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
            'font_color': COLOR_RED,
        })
        self.worksheet.write_string(1, 1, 'ООО "ЛЕРУА МЕРЛЕН ВОСТОК"', text_top)
        self.worksheet.write_string(2, 1, 'Магазин {}'.format(self.super_shop.title), text_top)
        self.worksheet.write_rich_string(3, 1,
            text_top, 'ТАБЕЛЬ УЧЕТА РАБОЧЕГО ВРЕМЕНИ ',
            text_top_red, '{}  {}г.'.format(
                self.MONTH_NAMES[self.month.month].upper(),
                self.month.year
            )
        )
        self.worksheet.write_string(5, 1, 'Отдел: ', text_top_red)
        self.worksheet.write_string(5, 2, self.shop.title, text_top)

        #
        # work month info
        text_f = self.workbook.add_format({
            'font_size': 10,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
            'border': 1,
        })
        number_f = self.workbook.add_format({
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'font_color': COLOR_RED,
            'border': 1,
        })
        self.worksheet.write_string('C8', 'Календарные дни', text_f)
        self.worksheet.write_number('D8', len(self.prod_days), number_f)

        self.worksheet.write_string('C9', 'Рабочие дни', text_f)
        self.worksheet.write_number(
            'D9',
            len(list(filter(lambda x: x.type in ProductionDay.WORK_TYPES, self.prod_days))),
            number_f
        )

        self.worksheet.write_string('C10', 'Вых/Празд дни', text_f)
        self.worksheet.write_number(
            'D10',
            len(list(filter(lambda x: x.type==ProductionDay.TYPE_HOLIDAY, self.prod_days))),
            number_f
        )

        text_f = self.workbook.add_format({
            'font_size': 10,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
            'bg_color': COLOR_YELLOW,
            'border': 1,
        })
        number_f = self.workbook.add_format({
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'font_color': COLOR_RED,
            'bg_color': COLOR_YELLOW,
            'border': 1,
        })
        self.worksheet.write_string('C11', 'Запланированные часы', text_f)
        self.worksheet.write_number(
            'D11',
            sum(map(lambda x: ProductionDay.WORK_NORM_HOURS[x.type], self.prod_days)),
            number_f
        )

        #
        # add workday types:
        day_type = {
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'border': 1,
        }

        day_text_d = {
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
        }
        day_text = self.workbook.add_format(day_text_d)

        def add_seria(seria_types, col):
            for it_row, type in enumerate(seria_types):
                d_type = dict(day_type)
                d_type.update({
                    'font_color': self.WORKERDAY_TYPE_COLORS[type[0]][0],
                    'bg_color': self.WORKERDAY_TYPE_COLORS[type[0]][1],
                })
                d_type = self.workbook.add_format(d_type)

                self.worksheet.write_string(1 + it_row, col, type[1], d_type)
                self.worksheet.write_string(1 + it_row, col + 1, type[2], day_text)
            return it_row

        seria_types = (
             (WorkerDay.Type.TYPE_WORKDAY.value, '8', ' - явка'),
             (WorkerDay.Type.TYPE_WORKDAY.value, '8_1', ' - явка с ночными часами'),
             ('night_work', '7', ' - явка с ночными часами'),
             (WorkerDay.Type.TYPE_BUSINESS_TRIP.value, 'К', ' - командировка'),
             (WorkerDay.Type.TYPE_HOLIDAY.value, 'В', ' - выходной день'),
             (WorkerDay.Type.TYPE_HOLIDAY_WORK.value, 'В8', ' - работа в выходной день'),
             (WorkerDay.Type.TYPE_ABSENSE.value, 'Н', ' - неявки до выяснения обстоятельств'),
             (WorkerDay.Type.TYPE_REAL_ABSENCE.value, 'ПР', ' - прогул на основании акта'),
             (WorkerDay.Type.TYPE_SICK.value, 'Б', ' - больничный лист (при '),
        )

        it_row = add_seria(seria_types, 6)

        day_text_d['font_color'] = COLOR_RED
        self.worksheet.write_string(1 + it_row, 7, 'наличии его в службе персонала) ', self.workbook.add_format(day_text_d))
        day_text_d['font_color'] = COLOR_BLACK
        # add second seria

        seria_types = (
            (WorkerDay.Type.TYPE_VACATION.value, 'ОТ', ' - отпуск'),
            (WorkerDay.Type.TYPE_EXTRA_VACATION.value, 'ОД', ' - доп. отпуск'),
            (WorkerDay.Type.TYPE_TRAIN_VACATION.value, 'У', ' - учебный отпуск'),
            (WorkerDay.Type.TYPE_SELF_VACATION.value, 'ДО', ' - отпуск за свой счет'),
            (WorkerDay.Type.TYPE_SELF_VACATION_TRUE.value, 'ОЗ', ' - за свой счет по уважительной причине'),
            (WorkerDay.Type.TYPE_GOVERNMENT.value, 'Г', ' - гос. обязанности'),
            (WorkerDay.Type.TYPE_REAL_ABSENCE.value, 'ОВ', ' - выходние дни по уходу'),
            (WorkerDay.Type.TYPE_MATERNITY.value, 'Б', ' - больничный лист (при '),
        )
        it_row = add_seria(seria_types, 18)
        self.worksheet.write_string(1 + it_row, 19, 'за детьми ивалидами,  дополнительный выходной доноров', day_text)
        self.worksheet.write_string(2 + it_row, 19, ' - б/л по беремености и родам', day_text)
        self.worksheet.write_string(3 + it_row, 19, ' - отпуск по уходу за ребенком до 3-х лет', day_text)

        #
        # add left info
        text_format_d = {
            'font_size': 10,
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'border': 1,
            'top': 2,
        }
        text_format = self.workbook.add_format(text_format_d)
        text_format_d['top'] =1
        text_format2 = self.workbook.add_format(text_format_d)

        self.worksheet.merge_range('A14:A15', '№', text_format)
        self.worksheet.merge_range('B14:B15', 'ФИО', text_format)
        self.worksheet.write_string('C14', 'ДОЛЖНОСТЬ', text_format)
        self.worksheet.write_string('D14', 'Date d\'entrée', text_format)

        self.worksheet.merge_range('E14:AI14', 'отметки о явках и неявках на работу по числам месяца', text_format)

        self.worksheet.write_string('A16', 'TN', text_format2)
        self.worksheet.write_string('B16', 'FIO', text_format2)
        self.worksheet.write_string('C16', 'APPOINT', text_format2)
        self.worksheet.write_string('D16', 'DATE_IN', text_format2)

        # add right info



    def fill_table(self, workdays, triplets):
        pass


    def add_xlsx_functions(self, users_info):
        pass


    def add_sign(self, row, col=3):
        self.worksheet.write_string(
            row,
            col,
            'Руководитель  отдела   /  __________________  /  ___________________________ / ',
            self.workbook.add_format(self.default_text_settings)
        )