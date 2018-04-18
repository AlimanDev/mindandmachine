import os
import pandas
from datetime import datetime, timedelta

from src.util.collection import range_u


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


def gen_frame(dt_from, dt_to):
    header = [
        ['', '', ''] + [PrintHelper.get_weekday_name(x) for x in range_u(dt_from, dt_to, timedelta(days=1))],
        ['№', 'ФИО', 'должность'] + [x.date() for x in range_u(dt_from, dt_to, timedelta(days=1))]
    ]

    return header


def print_to_file(path, dt_from, dt_to):
    # df = pandas.DataFrame([
    #     [1010, 2020, 3030, 202220, 1515, 3030, 4545],
    #     [.1, .2, .33, .25, .5, .75, .45],
    # ])

    df = pandas.DataFrame(gen_frame(dt_from, dt_to))
    writer = pandas.ExcelWriter(path, engine='xlsxwriter')
    df.to_excel(writer, sheet_name='Sheet1', header=False, index=False)
    writer.save()


def run():
    path = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(path, 'test.xlsx')
    if os.path.isfile(file_path):
        os.remove(file_path)

    print_to_file(
        path=file_path,
        dt_from=datetime(year=2018, month=5, day=1),
        dt_to=datetime(year=2018, month=6, day=1) - timedelta(days=1)
    )
