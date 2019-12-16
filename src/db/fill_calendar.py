"""
launch from shell

./manage.py shell
from src.db.works.fill_production_calendar import fill_calendar

Examples:
    fill_calendar.fill_month(2018, 2019) -- only for months
    fill_calendar.fill_days('2018.1.1', '2019.1.1')  -- only for production days
    fill_calendar.main('2018.1.1', '2019.1.1') -- for both months and days

"""
import pandas as pd
import datetime
from calendar import monthrange
from src.db.models import (
    ProductionDay
)

# произдственный календарь время от времени обновляется
# csv скачивать отсюда (какой-то гос сайт с открытыми данными)
# https://data.gov.ru/opendata/7708660670-proizvcalendar (мб со временем ссылка поменяется,но все равно сайт тотже)

month_dict = {
    1: 'январь',
    2: 'февраль',
    3: 'март',
    4: 'апрель',
    5: 'май',
    6: 'июнь',
    7: 'июль',
    8: 'август',
    9: 'сентябрь',
    10: 'октябрь',
    11: 'ноябрь',
    12: 'декабрь',
}


# def fill_months(from_year, to_year):
#     """
#     including boundaries (from_year <= year <= to_year)
#     Args:
#          from_year(int): e.g. 2018
#          to_year(int): e.g. 2020
#     """
#     data = pd.read_csv(
#         'src/db/work_data.csv',
#         index_col='Год/Месяц'
#     )

#     for year in range(from_year, to_year + 1):
#         year_data = data.loc[year]
#         for month_num, month_name in month_dict.items():
#             month_data = year_data[month_name.title()].split(',')
#             dt_first = datetime.date(year, month_num, 1)
#             total_days = monthrange(year, month_num)[1]
#             short_days = len([day for day in month_data if '*' in day])
#             norm_work_days = total_days - len(month_data) + short_days
#             norm_work_hours = norm_work_days * 8 - short_days  # один день со звездочкой -- 7часовой рабочий день
#             ProductionMonth.objects.update_or_create(
#                 dt_first=dt_first,
#                 defaults={
#                     'total_days': total_days,
#                     'norm_work_days': norm_work_days,
#                     'norm_work_hours': norm_work_hours
#                 }
#             )


def fill_days(from_date, to_date, region_id):
    """
    including boundaries
    Args:
        from_date(str): e.g. '2018.1.1'
        to_date(str): e.g. '2019.1.1'
    """
    data = pd.read_csv(
        'src/db/work_data.csv',
        index_col='Год/Месяц'
    )

    from_year = int(from_date.split('.')[0])
    to_year = int(to_date.split('.')[0])

    for year in range(from_year, to_year + 1):
        year_data = data.loc[year]
        for month_num, month_name in month_dict.items():
            month_data = year_data[month_name.title()].split(',')
            total_days = monthrange(year, month_num)[1]
            short_days = [day.replace('*', '') for day in month_data if '*' in day]
            for day in range(total_days):
                dt = datetime.date(year, month_num, day + 1)
                if str(dt.day) in short_days:
                    day_type = ProductionDay.TYPE_SHORT_WORK
                elif str(dt.day) in month_data:
                    day_type = ProductionDay.TYPE_HOLIDAY
                else:
                    day_type = ProductionDay.TYPE_WORK
                ProductionDay.objects.update_or_create(
                    dt=dt,
                    region_id=region_id,
                    defaults={
                        'type': day_type,
                        'is_celebration': False,
                    }
                )


def main(from_date, to_date, region_id):
    """
    including boundaries
    Args:
        from_date(str): e.g. '2018.1.1'
        to_date(str): e.g. '2019.1.1'
    """
    fill_days(from_date=from_date, to_date=to_date, region_id=region_id)

    from_date = datetime.datetime.strptime(from_date, '%Y.%m.%d').date()
    to_date = datetime.datetime.strptime(to_date, '%Y.%m.%d').date()
    # fill_months(from_year=from_date.year, to_year=to_date.year)
