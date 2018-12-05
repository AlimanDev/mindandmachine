import pandas as pd
import datetime
from calendar import monthrange
from src.db.models import (
    ProductionMonth,
    ProductionDay
)

# произдственный календарь время от времени обновляется
# csv скачивать отсюда (какой-то гос сайт с открытыми данными)
# https://data.gov.ru/opendata/7708660670-proizvcalendar (мб со временем ссылка поменяется,но все равно сайт тотже)


def fill_months(from_year, to_year):  # all including boundaries, e.g. 2015<=year<=2019
    file = pd.read_csv(
        'src/db/works/fill_production_calendar/work_data.csv',
        index_col=False,
        sep=';',
        names=['dts', 'types']
    )
    data = file['dts']
    from_year_index, to_year_index = None, None
    for year_index in range(1, data.shape[0]):
        if int(data[year_index].split(',')[0]) == from_year:
            from_year_index = year_index
        if int(data[year_index].split(',')[0]) == to_year:
            to_year_index = year_index
    if not from_year_index or not to_year_index:
        raise ValueError('не смог определить от какого до какого года работать.')

    for index in range(from_year_index, to_year_index + 1):
        year_data = data[index].split(',"')
        year = int(year_data[0])  # e.g. 2013
        for month in range(1, 13):
            month_data = year_data[month].split(',')
            if month == 12:
                last_day_index = month_data.index([day for day in month_data if '"' in day][0])
                month_data = month_data[:last_day_index + 1]
            month_data[-1] = month_data[-1].replace('"', '')
            dt_first = datetime.date(year, month, 1)
            total_days = monthrange(year, month)[1]
            short_days = len([day for day in month_data if '*' in day])
            norm_work_days = total_days - len(month_data) + short_days
            norm_work_hours = norm_work_days * 8 - short_days  # один день со звездочкой -- 7часовой рабочий день
            ProductionMonth.objects.update_or_create(
                dt_first=dt_first,
                defaults={
                    'total_days': total_days,
                    'norm_work_days': norm_work_days,
                    'norm_work_hours': norm_work_hours
                }
            )


def fill_days(from_date, to_date):
    """
    Args:
        from_date(str): '2018.1.1', including
        to_date(str): '2019.1.1' , including
    """
    file = pd.read_csv(
        'src/db/works/fill_production_calendar/work_data.csv',
        index_col=False,
        sep=';',
        names=['dts', 'types']
    )
    data = file['dts']
    from_year_index, to_year_index = None, None
    from_date = datetime.datetime.strptime(from_date, '%Y.%m.%d').date()
    to_date = datetime.datetime.strptime(to_date, '%Y.%m.%d').date()
    for year_index in range(1, data.shape[0]):
        if int(data[year_index].split(',')[0]) == from_date.year:
            from_year_index = year_index
        if int(data[year_index].split(',')[0]) == to_date.year:
            to_year_index = year_index
    if not from_year_index or not to_year_index:
        raise ValueError('не смог определить от какого до какого года работать.')

    for index in range(from_year_index, to_year_index + 1):
        year_data = data[index].split(',"')
        year = int(year_data[0])  # e.g. 2013
        for month in range(1, 13):
            month_data = year_data[month].split(',')
            if month == 12:
                last_day_index = month_data.index([day for day in month_data if '"' in day][0])
                month_data = month_data[:last_day_index + 1]
            month_data[-1] = month_data[-1].replace('"', '')
            total_days = monthrange(year, month)[1]
            short_days = [day for day in month_data if '*' in day]
            short_days = [no_star.replace('*', '') for no_star in short_days]
            for day in range(total_days):
                if datetime.date(year, month, day + 1) > to_date:
                    break
                dt = datetime.date(year, month, day + 1)
                if str(dt.day) in short_days:
                    day_type = ProductionDay.TYPE_SHORT_WORK
                elif str(dt.day) in month_data:
                    day_type = ProductionDay.TYPE_HOLIDAY
                else:
                    day_type = ProductionDay.TYPE_WORK
                ProductionDay.objects.update_or_create(
                    dt=dt,
                    defaults={
                        'type': day_type,
                        'is_celebration': False
                    }
                )

            else:
                continue
            break
        else:
            continue
        break


def main(from_date, to_date):
    """
    Args:
        from_date(str): '2018.1.1', including
        to_date(str): '2019.1.1' , including
    """
    fill_days(from_date=from_date, to_date=to_date)

    from_date = datetime.datetime.strptime(from_date, '%Y.%m.%d').date()
    to_date = datetime.datetime.strptime(to_date, '%Y.%m.%d').date()
    fill_months(from_year=from_date.year, to_year=to_date.year)
