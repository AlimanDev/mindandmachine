from .base_class import Xlsx_base
from math import ceil
from src.db.models import (
    ProductionDay,
    WorkerDay,
)
from src.util.collection import group_by
from .colors import *
import datetime
import json


class Tabel_xlsx(Xlsx_base):
    # (font; background)
    WORKERDAY_TYPE_COLORS = {
        WorkerDay.Type.TYPE_WORKDAY.value: (COLOR_BLACK, COLOR_WHITE),
        WorkerDay.Type.TYPE_BUSINESS_TRIP.value: (COLOR_RED, COLOR_WHITE),
        WorkerDay.Type.TYPE_HOLIDAY.value: (COLOR_BLACK, COLOR_GREEN),
        WorkerDay.Type.TYPE_HOLIDAY_WORK.value: (COLOR_BLACK, COLOR_GREEN),
        WorkerDay.Type.TYPE_ABSENSE.value: (COLOR_BLACK, COLOR_YELLOW2),
        WorkerDay.Type.TYPE_REAL_ABSENCE.value: (COLOR_BLACK, COLOR_RED),
        WorkerDay.Type.TYPE_SICK.value: (COLOR_BLACK, COLOR_1),
        WorkerDay.Type.TYPE_VACATION.value: (COLOR_BLACK, COLOR_BLUE),
        WorkerDay.Type.TYPE_EXTRA_VACATION.value: (COLOR_RED, COLOR_BLUE),
        WorkerDay.Type.TYPE_TRAIN_VACATION.value: (COLOR_BLACK, COLOR_DARK_BLUE),
        WorkerDay.Type.TYPE_SELF_VACATION.value: (COLOR_BLACK, COLOR_BLUE2),
        WorkerDay.Type.TYPE_SELF_VACATION_TRUE.value: (COLOR_BLACK, COLOR_LITE_GREEN),
        WorkerDay.Type.TYPE_GOVERNMENT.value: (COLOR_BLACK, COLOR_PINK3),
        WorkerDay.Type.TYPE_MATERNITY.value: (COLOR_BLACK, COLOR_YELLOW3),
        WorkerDay.Type.TYPE_MATERNITY_CARE.value: (COLOR_BLACK, COLOR_PURPLE),
        WorkerDay.Type.TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE.value: (COLOR_BLACK, COLOR_GREEN2),
        WorkerDay.Type.TYPE_ETC.value: (COLOR_GREY, COLOR_GREY),
        WorkerDay.Type.TYPE_EMPTY.value: (COLOR_GREY, COLOR_GREY),
        WorkerDay.Type.TYPE_QUALIFICATION.value: (COLOR_GREY, COLOR_GREY),

        'night_work': (COLOR_BLACK, COLOR_PINK2),

    }

    WORKERDAY_TYPE_VALUE = {
        WorkerDay.Type.TYPE_BUSINESS_TRIP.value: 'К',
        WorkerDay.Type.TYPE_HOLIDAY.value: 'В',
        WorkerDay.Type.TYPE_ABSENSE.value: 'Н',
        WorkerDay.Type.TYPE_REAL_ABSENCE.value: 'ПР',
        WorkerDay.Type.TYPE_QUALIFICATION.value: 'КВ',
        WorkerDay.Type.TYPE_SICK.value: 'Б',
        WorkerDay.Type.TYPE_VACATION.value: 'ОТ',
        WorkerDay.Type.TYPE_EXTRA_VACATION.value: 'ОД',
        WorkerDay.Type.TYPE_TRAIN_VACATION.value: 'У',
        WorkerDay.Type.TYPE_SELF_VACATION.value: 'ДО',
        WorkerDay.Type.TYPE_SELF_VACATION_TRUE.value: 'ОЗ',
        WorkerDay.Type.TYPE_GOVERNMENT.value: 'Г',
        # WorkerDay.Type.TYPE_MATERNITY.value: 'Р',
        WorkerDay.Type.TYPE_MATERNITY.value: 'ОЖ',
        WorkerDay.Type.TYPE_MATERNITY_CARE.value: 'Р',
        WorkerDay.Type.TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE.value: 'ОВ',
        WorkerDay.Type.TYPE_ETC.value: '',
        WorkerDay.Type.TYPE_EMPTY.value: '',
    }

    WORKERDAY_TYPE_CHANGE2HOLIDAY = [
        WorkerDay.Type.TYPE_MATERNITY.value,
        WorkerDay.Type.TYPE_MATERNITY_CARE.value,
        WorkerDay.Type.TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE.value
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.day_type = {
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'center',
            'border': 1,
        }

    def format_cells(self, users_len):
        def set_rows(row1, row2, heigth):
            for row in range(row1, row2 + 1):
                self.worksheet.set_row(row, heigth)

        normalized = 6.23820623
        self.worksheet.set_column(0, 0, 80 / normalized)
        self.worksheet.set_column(1, 1, 200 / normalized)
        self.worksheet.set_column(2, 2, 160 / normalized)
        self.worksheet.set_column(3, 3, 100 / normalized)

        self.worksheet.set_column(4, 5, 100 / normalized, None, {'hidden': True})

        self.worksheet.set_column(6, 36, 40 / normalized)
        self.worksheet.set_column(37, 37, 50 / normalized)
        self.worksheet.set_column(38, 63, 32 / normalized)

        self.worksheet.set_column(64, 73, 20 / normalized, None, {'hidden': True})
        self.worksheet.set_column(74, 77, 90 / normalized)

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
        self.worksheet.write_string(2, 1, 'Магазин: {}'.format(self.shop.title), text_top)
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
            len(list(filter(lambda x: x.type == ProductionDay.TYPE_HOLIDAY, self.prod_days))),
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
        self.worksheet.write_number('D11', self.prod_month.norm_work_hours, number_f)

        #
        # add workday types:
        day_text_d = {
            'font_size': 12,
            'font_name': 'Arial',
            'bold': True,
            'align': 'fill',
        }
        day_text = self.workbook.add_format(day_text_d)

        def add_seria(seria_types, col):
            for it_row, type in enumerate(seria_types):
                d_type = dict(self.day_type)
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

        it_row = add_seria(seria_types, 8)

        day_text_d['font_color'] = COLOR_RED
        self.worksheet.write_string(2 + it_row, 9, 'наличии его в службе персонала) ',
                                    self.workbook.add_format(day_text_d))
        day_text_d['font_color'] = COLOR_BLACK
        # add second seria

        seria_types = (
            (WorkerDay.Type.TYPE_VACATION.value, 'ОТ', ' - отпуск'),
            (WorkerDay.Type.TYPE_EXTRA_VACATION.value, 'ОД', ' - доп. отпуск'),
            (WorkerDay.Type.TYPE_TRAIN_VACATION.value, 'У', ' - учебный отпуск'),
            (WorkerDay.Type.TYPE_SELF_VACATION.value, 'ДО', ' - отпуск за свой счет'),
            (WorkerDay.Type.TYPE_SELF_VACATION_TRUE.value, 'ОЗ', ' - за свой счет по уважительной причине'),
            (WorkerDay.Type.TYPE_GOVERNMENT.value, 'Г', ' - гос. обязанности'),
            (WorkerDay.Type.TYPE_MATERNITY.value, 'Р', ' - б/л по беремености и родам'),
            (WorkerDay.Type.TYPE_MATERNITY_CARE.value, 'ОЖ', ' - отпуск по уходу за ребенком до 3-х лет'),

            (WorkerDay.Type.TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE.value, 'ОВ', ' - выходние дни по уходу'),
        )
        it_row = add_seria(seria_types, 20)
        self.worksheet.write_string(2 + it_row, 21, 'за детьми ивалидами,  дополнительный выходной доноров', day_text)

        # self.worksheet.write_string(3 + it_row, 21, ' - б/л по беремености и родам', day_text)
        # self.worksheet.write_string(4 + it_row, 21, ' - отпуск по уходу за ребенком до 3-х лет', day_text)

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
        text_format_d['top'] = 1
        text_format2 = self.workbook.add_format(text_format_d)

        self.worksheet.merge_range('A14:A15', '№', text_format)
        self.worksheet.merge_range('B14:B15', 'ФИО', text_format)
        self.worksheet.write_string('C14', 'ДОЛЖНОСТЬ', text_format)
        self.worksheet.write_string('D14', 'Date d\'entrée', text_format)
        self.worksheet.write_string('E14', 'Rayon', text_format)
        self.worksheet.write_string('F14', 'ЗАРПЛАТА', text_format)

        self.worksheet.merge_range('G14:AK14', 'отметки о явках и неявках на работу по числам месяца', text_format)

        self.worksheet.write_string('A16', 'TN', text_format2)
        self.worksheet.write_string('B16', 'FIO', text_format2)
        self.worksheet.write_string('C16', 'APPOINT', text_format2)
        self.worksheet.write_string('D16', 'DATE_IN', text_format2)
        self.worksheet.write_string('E16', 'CODE', text_format2)
        self.worksheet.write_string('F16', 'ZP', text_format2)

        # add right info

    def _time2hours(self, tm_start, tm_end, breaks=None):
        diff_h = (tm_end.hour - tm_start.hour) + (tm_end.minute - tm_start.minute) / 60
        if diff_h < 0:
            diff_h += 24
        if (breaks is not None) and len(breaks):
            i = 0
            # print(breaks, diff_h)
            while (len(breaks) > i) and not (breaks[i][0] <= diff_h < breaks[i][1]):
                i += 1
            if len(breaks) == i:
                i -= 1
            diff_h -= breaks[i][2]
        return diff_h

    def _count_time(self, tm_start, tm_end, hours=None, breaks=None, night_edges=None):
        if (night_edges is None) and (hours is not None):
            night_edges = (
                datetime.time(22, 0),
                datetime.time(6, 0),
            )

        total = str(int(self._time2hours(tm_start, tm_end, breaks) + 0.75))
        night_hs = 'all'
        if night_edges[0] > tm_start:
            # day_hs = self._time2hours(tm_start, night_edges[0])
            night_hs = int(self._time2hours(night_edges[0], tm_end) if (night_edges[0] < tm_end) or (
                        night_edges[1] >= tm_end) else 0)
            # print(night_hs, night_edges[0] < tm_end, night_edges[1] >= tm_end)
        return total, night_hs

    def fill_table(self, workdays, employments, triplets, working_hours, row_s, col_s):
        """
        одинаковая сортировка у workdays и users должна быть
        :param workdays:
        :param employments:
        :param triplets:
        :return:
        """

        it = 0
        cell_format = dict(self.day_type)
        n_workdays = len(workdays)
        for row_shift, employment in enumerate(employments):
            for day in range(len(self.prod_days)):

                if (it < n_workdays) and (workdays[it].employment_id == employment.id) and (day + 1 == workdays[it].dt.day):
                    wd = workdays[it]
                    if wd.type == WorkerDay.Type.TYPE_WORKDAY.value:
                        total_h, night_h = self._count_time(wd.dttm_work_start.time(), wd.dttm_work_end.time(), (0, 0), triplets)
                        if night_h == 'all':  # night_work
                            wd.type = 'night_work'
                        if (type(night_h) != str) and (night_h > 0):
                            text = '{}_{}'.format(total_h, night_h)
                        else:
                            text = str(total_h)

                    elif wd.type == WorkerDay.Type.TYPE_HOLIDAY_WORK.value:
                        total_h = ceil(self._time2hours(wd.dttm_work_start.time(), wd.dttm_work_end.time(), triplets))
                        text = 'В{}'.format(total_h)

                    elif (wd.type in self.WORKERDAY_TYPE_CHANGE2HOLIDAY) \
                            and (self.prod_days[day].type == ProductionDay.TYPE_HOLIDAY):
                        wd.type = WorkerDay.Type.TYPE_HOLIDAY.value
                        text = self.WORKERDAY_TYPE_VALUE[wd.type]

                    else:
                        text = self.WORKERDAY_TYPE_VALUE[wd.type]
                    cell_format.update({
                        'font_color': self.WORKERDAY_TYPE_COLORS[wd.type][0],
                        'bg_color': self.WORKERDAY_TYPE_COLORS[wd.type][1],
                    })

                    it += 1
                else:
                    text = ''
                    cell_format.update({
                        'font_color': COLOR_BLACK,
                        'bg_color': COLOR_GREY,
                    })

                self.worksheet.write_string(
                    row_s + row_shift * 2,
                    col_s + day,
                    text,
                    self.workbook.add_format(cell_format)
                )
                dt = self.month.replace(day=day+1)
                user_working_hours = working_hours.get(employment.user_id, {}).get(dt, 0)
                user_working_hours = user_working_hours if user_working_hours else 0
                breaktime = 0
                for triplet in triplets:
                    if triplet[0] <= user_working_hours and triplet[1] >= user_working_hours:
                        breaktime = triplet[2]
                self.worksheet.write(
                    row_s + row_shift * 2 + 1,
                    col_s + day,
                    round(max(user_working_hours - breaktime, 0)),
                    self.workbook.add_format(cell_format)
                )

    def _write_formula(self, row, n_rows, col, formula, cell_format, extra_row=False):
        step = 2 if extra_row else 1
        n_rows *= step
        for r_ind in range(row, row + n_rows):
            # if extra_row:
            #     self.worksheet.merge_range(
            #         r_ind, col,
            #         r_ind + 1, col,
            #         "=" + formula.format(r_ind + 1),
            #         cell_format
            #     )
            # else:
            self.worksheet.write_formula(
                r_ind, col,
                formula.format(r_ind + 1),
                cell_format
            )

    def _write_names_in_row(self, row, col, names, cell_format):
        for col_offset in range(len(names)):
            self.worksheet.write_string(row, col + col_offset, names[col_offset], cell_format)

    def add_xlsx_functions(self, n_users, row, col, extra_row=False):
        cell_format = dict(self.day_type)
        cell_format['bg_color'] = COLOR_PINK

        # workdays
        cell_f = self.workbook.add_format(cell_format)
        self.worksheet.write_string(row, col, 'план. Р/дни', cell_f)
        self.worksheet.write_string(row + 1, col, '', cell_f)
        self.worksheet.write_string(row + 2, col, '', cell_f)
        self.worksheet.write_string(row + 3, col, 'pl_days', cell_f)

        self._write_formula(row + 4, n_users, col, 'AN{0}+AT{0}+AU{0}+AV{0}', cell_f, extra_row)

        # other
        cell_format['bg_color'] = COLOR_WHITE
        cell_format['font_size'] = 10
        cell_f = self.workbook.add_format(cell_format)

        self._write_names_in_row(row, col + 1, [
            'часы', 'дни', 'Выхо', 'дни', 'праз',
            'к-во выход. и празд. дней', 'ОТ', 'Б',
            'Н', 'п', 'Кален дни', '9', '10',
            '50%', '11', '12', '100%', '50%',
            '50%', '200 %', '', 'д ноч', '20 %',
            'к-во дней  часов неявок', 'ночные'
        ], cell_f)

        self._write_names_in_row(row + 3, col + 1, [
            'f_hours', 'f_days', 'fh_days', 'pl_days2', 'f_pr_days',
            'vihodn', 'otpusk', 'boln',
            'nejavka', 'prazd', 'k_days', 's9', 's10',
            's10', 's11', 's12', 'sverh_100', 'sverh_50',
            'sverh_total', '', '', '', '',
            '', 'noch', 'proezd',
            '', 'ОД', 'ДО', 'У', '', '', '', '', '', '',
        ], cell_f)

        # неполная функция -- есть варианты которые не учитываются
        self._write_formula(
            row + 4, n_users, col + 1,
            '=COUNTIF(G{0}:AK{0}, "В1")*1 + COUNTIF(G{0}:AK{0},"В2")*2+COUNTIF(G{0}:AK{0},"В3")*3+COUNTIF(G{0}:AK{0},"В4")*4+'
            'COUNTIF(G{0}:AK{0},"В5")*5+COUNTIF(G{0}:AK{0},"В6")*6+COUNTIF(G{0}:AK{0},"В7")*7+COUNTIF(G{0}:AK{0},"В8")*8+'
            'COUNTIF(G{0}:AK{0},"5")*5+COUNTIF(G{0}:AK{0},"6")*6+'
            'COUNTIF(G{0}:AK{0},"7")*7+COUNTIF(G{0}:AK{0},"8")*8+COUNTIF(G{0}:AK{0},"9")*9+COUNTIF(G{0}:AK{0},"10")*10+'
            'COUNTIF(G{0}:AK{0},"11")*11+COUNTIF(G{0}:AK{0},"12")*12+COUNTIF(G{0}:AK{0},"К")*8+COUNTIF(G{0}:AK{0},"8_1")*8+'
            'COUNTIF(G{0}:AK{0},"8_2")*8+COUNTIF(G{0}:AK{0},"11_1")*11+COUNTIF(G{0}:AK{0},"11_7")*11+COUNTIF(G{0}:AK{0},"11_2")*11',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 2,
            'SUM(COUNTIF(G{0}:AK{0},"В1"),COUNTIF(G{0}:AK{0},"В2"),COUNTIF(G{0}:AK{0},"В3"),COUNTIF(G{0}:AK{0},"В4"),'
            'COUNTIF(G{0}:AK{0},"В5"),COUNTIF(G{0}:AK{0},"В6"),COUNTIF(G{0}:AK{0},"В7"),COUNTIF(G{0}:AK{0},"В8"),'
            'COUNTIF(G{0}:AK{0},"7"),COUNTIF(G{0}:AK{0},"8"),COUNTIF(G{0}:AK{0},"9"),COUNTIF(G{0}:AK{0},"10"),'
            'COUNTIF(G{0}:AK{0},"11"),COUNTIF(G{0}:AK{0},"12"),COUNTIF(G{0}:AK{0},"13"),COUNTIF(G{0}:AK{0},"14"),'
            'COUNTIF(G{0}:AK{0},"К"))',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 3,
            '(COUNTIF(G{0}:AK{0},"В1")*1+COUNTIF(G{0}:AK{0},"В2")*2+COUNTIF(G{0}:AK{0},"В3")*3+'
            'COUNTIF(G{0}:AK{0},"В4")*4+COUNTIF(G{0}:AK{0},"В5")*5+COUNTIF(G{0}:AK{0},"В6")*6+'
            'COUNTIF(G{0}:AK{0},"В7")*7+COUNTIF(G{0}:AK{0},"В8")*8+COUNTIF(G{0}:AK{0},"В9")*9+'
            'COUNTIF(G{0}:AK{0},"В10")*10+COUNTIF(G{0}:AK{0},"В11")*11+COUNTIF(G{0}:AK{0},"В12")*12)',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 4,
            '(AN{0}-AO{0})/8',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 6,
            '(COUNTIF(G{0}:AK{0},"В")+COUNTIF(G{0}:AK{0},"В1")+COUNTIF(G{0}:AK{0},"В2")+COUNTIF(G{0}:AK{0},"В3")+'
            'COUNTIF(G{0}:AK{0},"В4")+COUNTIF(G{0}:AK{0},"В5")+COUNTIF(G{0}:AK{0},"В6")+COUNTIF(G{0}:AK{0},"В7")+'
            'COUNTIF(G{0}:AK{0},"В8")+COUNTIF(G{0}:AK{0},"В9")+COUNTIF(G{0}:AK{0},"В10")+COUNTIF(G{0}:AK{0},"В11")+'
            'COUNTIF(G{0}:AK{0},"В12")+COUNTIF(G{0}:AK{0},"В13")+COUNTIF(G{0}:AK{0},"В14")+COUNTIF(G{0}:AK{0},"В15"))',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 7,
            'COUNTIF(G{0}:AK{0},"ОТ")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 8,
            'COUNTIF(G{0}:AK{0},"Б")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 9,
            'COUNTIF(G{0}:AK{0},"Н")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 10,
            'COUNTIF(G{0}:AK{0},"П")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 11,
            'SUM(AO{0}:AV{0})-AQ{0}',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 12,
            'COUNTIF(G{0}:AK{0},9)',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 13,
            'COUNTIF(G{0}:AK{0},10)',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 14,
            'AX{0}+AY{0}*2',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 15,
            'COUNTIF(G{0}:AK{0},11)',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 16,
            'COUNTIF(G{0}:AK{0},12)',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 17,
            'BA{0}+BB{0}*2',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 18,
            'BA{0}*2+BB{0}*2',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 19,
            'AZ{0}+BD{0}+BG{0}',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 20,
            '(AO{0}+AQ{0})*8',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 22,
            'COUNTIF(G{0}:AK{0},"7")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 23,
            'BH{0}*7',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 25,
            'COUNTIF(G{0}:AK{0},"7")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 28,
            'COUNTIF(G{0}:AK{0},"ОД")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 29,
            'COUNTIF(G{0}:AK{0},"ДО")',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 30,
            'COUNTIF(G{0}:AK{0},"У")',
            cell_f,
            extra_row,
        )

        self.worksheet.write_formula('BL13', 'SUM(BL14:BL31)', cell_f)

        cell_format = dict(self.day_type)
        cell_format['bg_color'] = COLOR_YELLOW
        cell_format['bold'] = True
        cell_format['align'] = 'center'

        cell_f = self.workbook.add_format(cell_format)
        cell_f.set_align('vjustify')

        self.worksheet.write_string('BW16', 'Текущий месяц', cell_f)
        self.worksheet.write_string('BX16', 'Закрытый месяц', cell_f)

        self._write_formula(
            row + 4, n_users, col + 37,
            'AM{0}-D11',
            cell_f,
            extra_row,
        )

        self._write_formula(
            row + 4, n_users, col + 38,
            '0',
            cell_f,
            extra_row,
        )

        cell_format['bg_color'] = COLOR_GREEN3
        cell_f = self.workbook.add_format(cell_format)
        cell_f.set_align('vjustify')

        self.worksheet.write_string('BY16', 'Закрытый месяц', cell_f)
        self._write_formula(
            row + 4, n_users, col + 39,
            'BW{0}+BX{0}',
            cell_f,
            extra_row,
        )

    def add_sign(self, row, col=3):
        self.worksheet.write_string(
            row,
            col,
            'Руководитель  отдела   /  __________________  /  ___________________________ / ',
            self.workbook.add_format(self.default_text_settings)
        )

    @staticmethod
    def change_for_inspection(month_norm_hours, workdays):
        break_triplets = json.loads(workdays[0].shop.break_triplets)

        workdays = group_by(workdays, group_key=lambda _: _.worker_id)
        actual_hours = {}

        def from_workday_to_holiday(wd):
            wd.type = WorkerDay.Type.TYPE_HOLIDAY.value
            wd.dttm_work_start = None
            wd.dttm_work_end = None

        def concat_breaks(duration, concat_type='sub'):
            """

            :param duration: worker day duration, in minutes
            :param concat_type: 'sub'/'add', add or subtract breaks to wd_duration
            :return: worker day duration minus breaks
            """
            needed_triplet = None
            for triplet in break_triplets:
                if triplet[0] < duration <= triplet[1]:
                    needed_triplet = triplet

            if needed_triplet:
                for break_item in needed_triplet[2]:
                    if concat_type == 'sub':
                        duration -= break_item
                    else:
                        duration += break_item
            return duration

        for worker_id in workdays.keys():
            actual_hours[worker_id] = 0
            for wd in workdays[worker_id]:
                if wd.dttm_work_start and wd.dttm_work_end:
                    hours_on_day = concat_breaks((wd.dttm_work_end - wd.dttm_work_start).total_seconds() / 60) / 60
                    actual_hours[worker_id] += hours_on_day
            if actual_hours[worker_id] > month_norm_hours:
                diff = actual_hours[worker_id] - month_norm_hours
                diff_days = ceil(diff) / 8

                worker_workdays_len = len(workdays[worker_id])
                each = worker_workdays_len // ceil(diff_days)
                days_to_change = ceil(diff_days)

                for i in range(1, worker_workdays_len):
                    if days_to_change == 1 and diff_days != int(diff_days):
                        for j in range(i, worker_workdays_len):
                            worker_day = workdays[worker_id][j]
                            if worker_day.type == WorkerDay.Type.TYPE_WORKDAY.value:
                                wd_duration = (worker_day.dttm_work_end - worker_day.dttm_work_start).total_seconds() / 60
                                no_breaks_duration = concat_breaks(wd_duration)
                                new_duration = no_breaks_duration * (1 - diff_days + int(diff_days))
                                worker_day.dttm_work_end = worker_day.dttm_work_start + datetime.timedelta(
                                    minutes=concat_breaks(new_duration, 'add')
                                )

                                days_to_change -= 1
                                break
                            if j == worker_workdays_len - 1:
                                worker_day.type = WorkerDay.Type.TYPE_WORKDAY.value
                                worker_day.dttm_work_start = workdays[worker_id][j - 1].dttm_work_start
                                wd_duration = 540
                                no_breaks_duration = concat_breaks(wd_duration)
                                new_duration = no_breaks_duration * (1 - diff_days + int(diff_days))
                                worker_day.dttm_work_end = worker_day.dttm_work_start + datetime.timedelta(
                                    minutes=concat_breaks(new_duration, 'add')
                                )
                                days_to_change -= 1
                                break
                    if days_to_change == 0:
                        break
                    if i % each == 0:
                        if workdays[worker_id][i].type == WorkerDay.Type.TYPE_WORKDAY.value:
                            from_workday_to_holiday(workdays[worker_id][i])
                            days_to_change -= 1
                        else:
                            for j in range(i, worker_workdays_len - days_to_change):
                                if workdays[worker_id][j].type == WorkerDay.Type.TYPE_WORKDAY.value:
                                    from_workday_to_holiday(workdays[worker_id][j])
                                    days_to_change -= 1
                                    break
                            each = worker_workdays_len - days_to_change

        work_days_list = []
        for worker_id in workdays.keys():
            for worker_day in workdays[worker_id]:
                work_days_list.append(worker_day)

        return work_days_list
