import numpy as np
import pandas as pd
import datetime


def get_timetable_from_file(path, st_time=datetime.time(6, 45), step=15, periods=70, gap=1, time_format='%H:%M'):
    data = pd.read_excel(path, header=None)
    periods += 1
    days_col = 2 + gap
    days = data.shape[1] // days_col
    if days != data.shape[1] / days_col:
        raise ValueError('not correct amount of columns in {}: {}'.format(path, data.shape[1]))

    dttm_min = datetime.datetime.combine(datetime.date.min, st_time)
    delta = datetime.timedelta
    str2time = datetime.datetime.strptime
    times = {(dttm_min + delta(minutes=i * step)).time(): i for i in range(periods)}
    # print(times)

    working_t = np.zeros((data.shape[0], days, periods))
    cashiers = data[0].values

    for ind_c in range(cashiers.shape[0]):
        for ind_d in range(days):
            try:
                start_w = str2time(data.iloc[ind_c, ind_d * days_col + 1], time_format).time()
                end_w = str2time(data.iloc[ind_c, ind_d * days_col + 2], time_format).time()

                working_t[ind_c, ind_d, times[start_w]:times[end_w]+1] = 1
            except (ValueError, TypeError):
                pass
    return cashiers, working_t


def get_cashiers_speeds(
        # cashiers,
        data,
        min_bills=1000,
        mean_speed=-1,
        max_bill_time=1800,
        normalize_val=60,
    ):
    empl_name_col = data.columns[0]
    bill_time_col = data.columns[1]


    cashiers_data = data #  [data[empl_name_col].isin(cashiers)]
    speeds = cashiers_data[cashiers_data[bill_time_col] < max_bill_time].groupby(empl_name_col)[bill_time_col].mean()
    amount = cashiers_data[cashiers_data[bill_time_col] < max_bill_time].groupby(empl_name_col)[bill_time_col].count()
    amount.name = 'count'

    speeds = pd.concat([speeds, amount], axis=1)
    maska = speeds['count'] < min_bills
    # prop = (speeds['count'][maska] / min_bills) ** 4
    if mean_speed == -1:
        mean_speed = speeds[maska == False][bill_time_col].mean()

    # speeds.loc[maska, bill_time_col] = prop * speeds.loc[maska, bill_time_col] + (1 - prop) * mean_speed
    speeds.loc[maska, bill_time_col] = mean_speed
    speeds.loc[:, bill_time_col] /= normalize_val
    return speeds.reset_index()


def FIO_join(
        table_1,
        table_2,
        format_1=('Surname', 'Name', 'Patronymic'),
        format_2=('Name', 'Surname'),
        col_fill_med='cash_t',
        col_fill_zero='count'
    ):
    """

    :param table_1:
    :param table_2:
    :param format_1:
    :param format_2:
    :param col_fill_med:  could be a list
    :param col_fill_zero: could be a list
    :return:
    """

    # table_1 = table_1.copy()
    table_2 = table_2.copy()
    empl_name_col = table_2.columns[0]
    for col in format_2:
        table_2[col] = ''

    # AA:  there is surnames with several words "Van Beek"
    table_2.loc[:, format_2] = pd.DataFrame([x.split()[:len(format_2)] for x in table_2[empl_name_col]]).values
    table_2.drop([empl_name_col], axis=1, inplace=True)
    join_columns = [x for x in format_1 if x in format_2]
    table_1 = pd.DataFrame([x.split()[:len(format_1)] for x in table_1], columns=format_1)
    result = table_1.merge(table_2, how='left', on=join_columns)

    # Duplicates
    join_count = result.groupby(join_columns).apply(len)
    duplicates = join_count.index[join_count > 1]
    if len(duplicates):
        print('There are some duplicates in cashiers or cashier_speeds')
        print(duplicates)

    # Filling NA's
    result.drop_duplicates(join_columns, inplace=True)
    if col_fill_med:
        result[col_fill_med].fillna(result[col_fill_med].median(axis=0), inplace=True)
    if col_fill_zero:
        result[col_fill_zero].fillna(0, inplace=True)
    return result
