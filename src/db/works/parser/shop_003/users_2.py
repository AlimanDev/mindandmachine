import os
from datetime import time, datetime, timedelta

import pandas

from src.db.models import WorkerDay, CashboxType, Cashbox, Shop, User, WorkerDayCashboxDetails, WorkerConstraint
from src.util.collection import range_u
from .users import SheetIndexHelper, range_i


class ParseHelper(object):
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


class ParseHelperD003(ParseHelper):
    @classmethod
    def parse_work_day_type(cls, value):
        work_times = {
            '1': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 00), time(16, 00)],
            '2': [WorkerDay.Type.TYPE_WORKDAY.value, time(8, 00), time(17, 00)],
            '3': [WorkerDay.Type.TYPE_WORKDAY.value, time(13, 00), time(22, 00)],
            '4': [WorkerDay.Type.TYPE_WORKDAY.value, time(15, 00), time(00, 00)],
            '7': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 00), time(18, 00)],
            '9': [WorkerDay.Type.TYPE_WORKDAY.value, time(13, 00), time(00, 00)],
            '10': [WorkerDay.Type.TYPE_WORKDAY.value, time(22, 00), time(6, 00)],

            # wtf?
            'уу': [WorkerDay.Type.TYPE_WORKDAY.value, time(10, 00), time(19, 00)],
            'дд': [WorkerDay.Type.TYPE_WORKDAY.value, time(13, 00), time(22, 00)],

            'в': [WorkerDay.Type.TYPE_HOLIDAY.value, None, None],
            'от': [WorkerDay.Type.TYPE_VACATION.value, None, None],
        }

        return work_times.get(str(value).lower(), [WorkerDay.Type.TYPE_EMPTY.value, None, None])


class ParseHelperD007(ParseHelper):
    @classmethod
    def parse_work_day_type(cls, value):
        work_times = {
            '1': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 00), time(16, 00)],
            '2': [WorkerDay.Type.TYPE_WORKDAY.value, time(11, 00), time(20, 00)],
            '3': [WorkerDay.Type.TYPE_WORKDAY.value, time(15, 00), time(00, 00)],

            'в': [WorkerDay.Type.TYPE_HOLIDAY.value, None, None],
            'от': [WorkerDay.Type.TYPE_VACATION.value, None, None],
        }

        return work_times.get(str(value).lower(), [WorkerDay.Type.TYPE_EMPTY.value, None, None])


class ParseHelperD012(ParseHelper):
    @classmethod
    def parse_work_day_type(cls, value):
        work_times = {
            '1': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 00), time(16, 00)],
            '2': [WorkerDay.Type.TYPE_WORKDAY.value, time(9, 00), time(18, 00)],
            '3': [WorkerDay.Type.TYPE_WORKDAY.value, time(13, 00), time(22, 00)],
            '4': [WorkerDay.Type.TYPE_WORKDAY.value, time(15, 00), time(00, 00)],
            '5': [WorkerDay.Type.TYPE_WORKDAY.value, time(10, 00), time(19, 00)],
            'у': [WorkerDay.Type.TYPE_WORKDAY.value, time(7, 0), time(19, 0)],
            'вч': [WorkerDay.Type.TYPE_WORKDAY.value, time(12, 0), time(0, 0)],
            'д': [WorkerDay.Type.TYPE_WORKDAY.value, time(12, 00), time(21, 00)],
            'в': [WorkerDay.Type.TYPE_HOLIDAY.value, None, None],
            'от': [WorkerDay.Type.TYPE_VACATION.value, None, None],
        }

        return work_times.get(str(value).lower(), [WorkerDay.Type.TYPE_EMPTY.value, None, None])


def load_users(manager_username, shop, data, year, month, column_cashbox_type, column_fio, row_date, row_begin, row_end, col_timetable_begin, col_timetable_end, parse_helper):
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
            password='qwerty003'
        )
        user.shop = shop
        user.first_name = 'Руководитель'
        user.middle_name = ' '
        user.last_name = 'Сектора'
        user.save()

    wd_create_error = 0

    counter = 0
    cashboxes_types = {x.name: x for x in CashboxType.objects.filter(shop_id=shop.id)}
    cashboxes = {c_name: Cashbox.objects.filter(type=c)[0] for c_name, c in cashboxes_types.items()}
    for row in range_i(row_begin, row_end):
        counter += 1

        try:
            first_name, middle_name, last_name = parse_helper.parse_fio(data[column_fio][row])
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
                cashbox_type_name = parse_helper.parse_cashbox_type(data[column_cashbox_type][row-i])
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
            dt = parse_helper.parse_date(year, month, data[col][row_date])
            workday_type, tm_work_start, tm_work_end = parse_helper.parse_work_day_type(data[col][row])
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
    shop = Shop.objects.create(super_shop=super_shop, full_interface=False, title='Электротовары', hidden_title='d003')
    load_users(
        manager_username='cs003.mag003',
        shop=shop,
        data=pandas.read_excel(os.path.join(path, 'users_2_d003_m05.xlsx'), 'май 2018', header=None),
        year=2018,
        month=5,
        column_cashbox_type='b',
        column_fio='c',
        row_date=11,
        row_begin=14,
        row_end=25,
        col_timetable_begin='d',
        col_timetable_end='ah',
        parse_helper=ParseHelperD003
    )

    dttm_from = datetime(year=1971, month=1, day=1)
    dttm_to = datetime(year=1971, month=1, day=1, hour=7)
    dttm_step = timedelta(minutes=30)
    for user in User.objects.filter(shop=shop):
        for i in range(7):
            for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
                WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())

    # # file #2
    shop = Shop.objects.create(super_shop=super_shop, full_interface=False, title='Сантехника', hidden_title='d007')
    load_users(
        manager_username='cs007.mag003',
        shop=shop,
        data=pandas.read_excel(os.path.join(path, 'users_2_d007_m05.xlsx'), 'май', header=None),
        year=2018,
        month=5,
        column_cashbox_type='a',
        column_fio='b',
        row_date=14,
        row_begin=17,
        row_end=32,
        col_timetable_begin='c',
        col_timetable_end='ag',
        parse_helper=ParseHelperD007
    )

    dttm_from = datetime(year=1971, month=1, day=1)
    dttm_to = datetime(year=1971, month=1, day=1, hour=7)
    dttm_step = timedelta(minutes=30)
    for user in User.objects.filter(shop=shop):
        for i in range(7):
            for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
                WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())

    # file #3
    shop = Shop.objects.create(super_shop=super_shop, full_interface=False, title='Декор', hidden_title='d012')
    load_users(
        manager_username='cs012.mag003',
        shop=shop,
        data=pandas.read_excel(os.path.join(path, 'users_2_d012_m05.xlsx'), 'МАЙ 2018', header=None),
        year=2018,
        month=5,
        column_cashbox_type='C',
        column_fio='D',
        row_date=13,
        row_begin=15,
        row_end=28,
        col_timetable_begin='E',
        col_timetable_end='AJ',
        parse_helper=ParseHelperD012
    )

    dttm_from = datetime(year=1971, month=1, day=1)
    dttm_to = datetime(year=1971, month=1, day=1, hour=7)
    dttm_step = timedelta(minutes=30)
    for user in User.objects.filter(shop=shop):
        for i in range(7):
            for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
                WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())
