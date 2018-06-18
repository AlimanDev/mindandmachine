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
        self.worksheet.write_string(2, 1, 'ООО "ЛЕРУА МЕРЛЕН ВОСТОК"', text_top)
        self.worksheet.write_string(3, 1, 'Магазин {}'.format(self.super_shop.title), text_top)
        self.worksheet.write_rich_string(4, 1,
            text_top, 'ТАБЕЛЬ УЧЕТА РАБОЧЕГО ВРЕМЕНИ ',
            text_top_red, '{}  {}г.'.format(
                self.MONTH_NAMES[self.month.month].upper(),
                self.month.year
            )
        )
        self.worksheet.write_string(6, 1, 'Отдел: ', text_top_red)
        self.worksheet.write_string(6, 2, self.shop.title, text_top)

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
        day_text = self.workbook.add_format({
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
        })

        seria1_types = (
             (WorkerDay.Type.TYPE_WORKDAY.value, '8', ' - явка'),
             (WorkerDay.Type.TYPE_WORKDAY.value, '8_3', ' - явка с ночными часами'),
             ('night_work', '7', ' - явка с ночными часами'),
             (WorkerDay.Type.TYPE_BUSINESS_TRIP.value, 'К', ' - командировка'),
             (WorkerDay.Type.TYPE_HOLIDAY.value, 'В', ' - выходной день'),
             (WorkerDay.Type.TYPE_HOLIDAY_WORK.value, 'В8', ' - работа в выходной день'),
             (WorkerDay.Type.TYPE_ABSENSE.value, 'Н', ' - неявки до выяснения обстоятельств'),
             (WorkerDay.Type.TYPE_REAL_ABSENCE.value, 'ПР', ' - прогул на основании акта'),
             (WorkerDay.Type.TYPE_SICK.value, 'Б', ' - больничный лист (при '),
        )

        for it_row, type in enumerate(seria1_types):
            d_type = dict(day_type)
            d_type.update({
                'font_color': self.WORKERDAY_TYPE_COLORS[type[0]][0],
                'bg_color': self.WORKERDAY_TYPE_COLORS[type[0]][1],
            })
            d_type = self.workbook.add_format(d_type)

            self.worksheet.write_string(1 + it_row, 6, type[1], d_type)
            self.worksheet.write_string(1 + it_row, 7, type[2], day_text)

        # add second seria



        # add left info


        # add right info



    def fill_table(self, workdays, triplets):
        pass


    def add_xlsx_functions(self, users_info):
        pass


    def add_sign(self, row, col=4):
        self.worksheet.write_string(
            row,
            col,
            'Руководитель  отдела   /  __________________  /  ___________________________ / ',

        )