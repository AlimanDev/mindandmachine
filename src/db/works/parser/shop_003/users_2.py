import os
from datetime import time, datetime, timedelta

import pandas

from src.db.models import WorkerDay, CashboxType, Cashbox, Shop, User, WorkerDayCashboxDetails, WorkerConstraint
from src.util.collection import range_u
from .users import SheetIndexHelper, range_i


class ParseHelper(object):
    @classmethod
    def parse_work_day_type(cls, value):
        work_times = {
            'у': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 0), time(19, 0)],
            'вч': [WorkerDay.Type.TYPE_WORKDAY.value, time(12, 0), time(0, 0)],
            'д': [WorkerDay.Type.TYPE_WORKDAY.value, time(10, 00), time(19, 00)],
            '1': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 00), time(16, 00)],
            '2': [WorkerDay.Type.TYPE_WORKDAY.value, time(9, 00), time(18, 00)],
            '3': [WorkerDay.Type.TYPE_WORKDAY.value, time(13, 30), time(22, 00)],
            '4': [WorkerDay.Type.TYPE_WORKDAY.value, time(15, 30), time(00, 00)],
            '5': [WorkerDay.Type.TYPE_WORKDAY.value, time(10, 30), time(19, 00)],
            'в': [WorkerDay.Type.TYPE_HOLIDAY.value, None, None],
            'от': [WorkerDay.Type.TYPE_HOLIDAY.value, None, None],
            'н': [WorkerDay.Type.TYPE_WORKDAY.value, time(21, 00), time(9, 00)]
        }

        return work_times.get(str(value).lower(), work_times['в'])

    @classmethod
    def parse_cashbox_type(cls, value):
        value = value.strip().lower()
        if value.endswith(' ст'):
            return None

        return value

    @classmethod
    def parse_fio(cls, value):
        value = {i: v for i, v in enumerate(value.strip().split())}
        last_name = value.get(0, '')
        first_name = value.get(1, '')
        middle_name = value.get(2, '')
        return first_name, middle_name, last_name

    @classmethod
    def parse_date(cls, year, month, value):
        if isinstance(value, datetime):
            return datetime(year=year, month=month, day=value.day)

        return datetime(year=year, month=month, day=int(value)).date()


def load_users(manager_username, shop, data, year, month, column_cashbox_type, column_fio, row_date, row_begin, row_end, col_timetable_begin, col_timetable_end):
    column_cashbox_type = SheetIndexHelper.get_column(column_cashbox_type)
    column_fio = SheetIndexHelper.get_column(column_fio)
    row_begin = SheetIndexHelper.get_row(row_begin)
    row_end = SheetIndexHelper.get_row(row_end)
    col_timetable_begin = SheetIndexHelper.get_column(col_timetable_begin)
    col_timetable_end = SheetIndexHelper.get_column(col_timetable_end)
    row_date = SheetIndexHelper.get_row(row_date)

    if manager_username is not None:
        user = User.objects.create_user(
            username=manager_username,
            email='q@q.com',
            password='bestcompany003'
        )
        user.shop = shop
        user.first_name = 'Иван'
        user.middle_name = ' '
        user.last_name = 'Иванов'
        user.save()

    wd_create_error = 0

    counter = 0
    cashboxes_types = {x.name: x for x in CashboxType.objects.filter(shop_id=shop.id)}
    cashboxes = {c_name: Cashbox.objects.filter(type=c)[0] for c_name, c in cashboxes_types.items()}
    for row in range_i(row_begin, row_end):
        counter += 1

        try:
            first_name, middle_name, last_name = ParseHelper.parse_fio(data[column_fio][row])
        except:
            continue

        try:
            user = User.objects.get(first_name=first_name, middle_name=middle_name, last_name=last_name)
        except User.DoesNotExist:
            user = User.objects.create_user(
                username='u_{}_{}_{}'.format(shop.id, counter, month),
                email='q@q.com',
                password='4242'
            )
            user.shop = shop
            user.work_type = User.WorkType.TYPE_5_2.value
            user.first_name = first_name
            user.middle_name = middle_name
            user.last_name = last_name
            user.save()

        for i in range(20):
            try:
                cashbox_type_name = ParseHelper.parse_cashbox_type(data[column_cashbox_type][row-i])
                break
            except:
                pass

        if cashbox_type_name is None:
            continue

        if cashbox_type_name in cashboxes_types:
            cashbox_type = cashboxes_types[cashbox_type_name]
            cashbox = cashboxes[cashbox_type_name]
        else:
            cashbox_type = CashboxType.objects.create(shop=shop, name=cashbox_type_name, is_stable=True)
            cashboxes_types[cashbox_type_name] = cashbox_type
            cashbox = Cashbox.objects.create(type=cashbox_type, number='1')
            cashboxes[cashbox_type_name] = cashbox

        for col in range_i(col_timetable_begin, col_timetable_end):
            dt = ParseHelper.parse_date(year, month, data[col][row_date])
            workday_type, tm_work_start, tm_work_end = ParseHelper.parse_work_day_type(data[col][row])
            is_wk = workday_type == WorkerDay.Type.TYPE_WORKDAY.value

            try:
                wd = WorkerDay.objects.create(
                    worker=user,
                    dt=dt,
                    type=workday_type,
                    worker_shop=shop,
                    tm_work_start=tm_work_start,
                    tm_work_end=tm_work_end
                )

                if is_wk:
                    wdcd = WorkerDayCashboxDetails.objects.create(
                        worker_day=wd,
                        on_cashbox=cashbox,
                        tm_from=tm_work_start,
                        tm_to=tm_work_end
                    )
            except:
                wd_create_error += 1

    print('wd_create_error', wd_create_error)


def run(path, super_shop):
    # file #1
    shop = Shop.objects.create(super_shop=super_shop, full_interface=False, title='Электротовары', hidden_title='electro')
    # load_users(
    #     manager_username='cs003.mag004',
    #     shop=shop,
    #     data=pandas.read_excel(os.path.join(path, 'users_2_a.xlsx'), 'апрель 18', header=None),
    #     year=2018,
    #     month=4,
    #     column_cashbox_type='c',
    #     column_fio='D',
    #     row_date=10,
    #     row_begin=12,
    #     row_end=22,
    #     col_timetable_begin='E',
    #     col_timetable_end='ah'
    # )
    #
    # load_users(
    #     manager_username=None,
    #     shop=shop,
    #     data=pandas.read_excel(os.path.join(path, 'users_2_a.xlsx'), 'май 18', header=None),
    #     year=2018,
    #     month=5,
    #     column_cashbox_type='c',
    #     column_fio='D',
    #     row_date=10,
    #     row_begin=12,
    #     row_end=22,
    #     col_timetable_begin='E',
    #     col_timetable_end='ai'
    # )
    #
    # dttm_from = datetime(year=1971, month=1, day=1)
    # dttm_to = datetime(year=1971, month=1, day=1, hour=7)
    # dttm_step = timedelta(minutes=30)
    # for user in User.objects.filter(shop=shop):
    #     for i in range(7):
    #         for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
    #             WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())
    #
    # # file #2
    # shop = Shop.objects.create(super_shop=super_shop, full_interface=False, title='Сантехника', hidden_title='santeh')
    # load_users(
    #     manager_username='cs007.mag004',
    #     shop=shop,
    #     data=pandas.read_excel(os.path.join(path, 'users_2_b.xls'), 'апрель', header=None),
    #     year=2018,
    #     month=4,
    #     column_cashbox_type='c',
    #     column_fio='D',
    #     row_date=10,
    #     row_begin=12,
    #     row_end=23,
    #     col_timetable_begin='E',
    #     col_timetable_end='ah'
    # )
    #
    # load_users(
    #     manager_username=None,
    #     shop=shop,
    #     data=pandas.read_excel(os.path.join(path, 'users_2_b.xls'), 'май', header=None),
    #     year=2018,
    #     month=5,
    #     column_cashbox_type='c',
    #     column_fio='D',
    #     row_date=10,
    #     row_begin=11,
    #     row_end=23,
    #     col_timetable_begin='E',
    #     col_timetable_end='ai'
    # )
    #
    # dttm_from = datetime(year=1971, month=1, day=1)
    # dttm_to = datetime(year=1971, month=1, day=1, hour=7)
    # dttm_step = timedelta(minutes=30)
    # for user in User.objects.filter(shop=shop):
    #     for i in range(7):
    #         for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
    #             WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())

    # file #3
    shop = Shop.objects.create(super_shop=super_shop, full_interface=False, title='Декор', hidden_title='dekor')
    load_users(
        manager_username='cs012.mag003',
        shop=shop,
        data=pandas.read_excel(os.path.join(path, 'users_2_c.xlsx'), 'Апрель 2018', header=None),
        year=2018,
        month=4,
        column_cashbox_type='B',
        column_fio='C',
        row_date=13,
        row_begin=15,
        row_end=38,
        col_timetable_begin='D',
        col_timetable_end='AH'
    )

    load_users(
        manager_username=None,
        shop=shop,
        data=pandas.read_excel(os.path.join(path, 'users_2_c.xlsx'), 'МАЙ 2018', header=None),
        year=2018,
        month=5,
        column_cashbox_type='B',
        column_fio='C',
        row_date=13,
        row_begin=15,
        row_end=38,
        col_timetable_begin='D',
        col_timetable_end='AI',
    )

    dttm_from = datetime(year=1971, month=1, day=1)
    dttm_to = datetime(year=1971, month=1, day=1, hour=7)
    dttm_step = timedelta(minutes=30)
    for user in User.objects.filter(shop=shop):
        for i in range(7):
            for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
                WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())
