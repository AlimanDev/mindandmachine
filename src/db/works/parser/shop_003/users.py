import math
import random

import pandas
import datetime
import os
from src.db.models import Shop, User, WorkerDay, CashboxType, Cashbox, WorkerDayCashboxDetails, WorkerCashboxInfo, PeriodDemand, WorkerConstraint
from src.util.collection import range_u


class Context(object):
    def __init__(self):
        self.shop = None


class SheetIndexHelper(object):
    __COLUMNS_MAPPING = None
    __COLUMNS_MAPPING_REVERSE = None

    @staticmethod
    def __create_columns_mapping():
        arr = 'abcdefghijklmnopqrstuvwxyz'
        m = {}
        i = 0

        # for 1-len name
        for c in arr:
            m[c] = i
            i += 1

        # for 2-len name
        for c1 in arr:
            for c2 in arr:
                m[c1 + c2] = i
                i += 1

        return m

    @classmethod
    def __check_columns_mapping(cls):
        if cls.__COLUMNS_MAPPING is None:
            cls.__COLUMNS_MAPPING = cls.__create_columns_mapping()
            cls.__COLUMNS_MAPPING_REVERSE = {v: k for k, v in cls.__COLUMNS_MAPPING.items()}

    @classmethod
    def get_indexes(cls, x, y):
        return cls.get_column(x), cls.get_row(y)

    @classmethod
    def get_column(cls, x):
        cls.__check_columns_mapping()
        return cls.__COLUMNS_MAPPING[x.lower()]

    @classmethod
    def get_row(cls, y):
        return y - 1

    @classmethod
    def print_indexes(cls, x, y):
        cls.__check_columns_mapping()
        print('column = {}, row = {}'.format(cls.__COLUMNS_MAPPING_REVERSE[x], y + 1))


class UserParseHelper(object):
    @classmethod
    def parse_fio(cls, value):
        value = {i: v for i, v in enumerate(value.strip().split())}
        last_name = value.get(0, 'DEFAULT')
        first_name = value.get(1, 'DEFAULT')
        middle_name = value.get(2, 'DEFAULT')
        return first_name, middle_name, last_name

    @classmethod
    def parse_workday_type(cls, value):
        if isinstance(value, datetime.time) or isinstance(value, datetime.datetime):
            return WorkerDay.Type.TYPE_WORKDAY.value

        if value == 'В':
            return WorkerDay.Type.TYPE_HOLIDAY.value

        if value == 'ОТ':
            return WorkerDay.Type.TYPE_VACATION.value

        if value == 'ОВ':  # что это?
            return WorkerDay.Type.TYPE_HOLIDAY.value

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_work_time(cls, value):
        if isinstance(value, datetime.time):
            return value

        if isinstance(value, datetime.datetime):
            return value.time()

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_date(cls, value):
        if isinstance(value, datetime.datetime):
            return value

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_cashbox_type_name(cls, value):
        mapping = {
            'инфо': 'Информация',
            'возв': 'Возврат',
            'гк': 'Главная касса',
            'оркк': 'ОРКК',
            'сверка': 'Сверка',
            'сц': 'СЦ'
        }

        if isinstance(value, str):
            value = value.lower()

        return mapping.get(value, 'Линия')


class DataParseHelper(object):
    @classmethod
    def parse_fio(cls, value):
        value = {i: v for i, v in enumerate(value.strip().split())}
        last_name = value.get(0, '')
        first_name = value.get(1, '')
        middle_name = value.get(2, '')
        return first_name, middle_name, last_name

    @classmethod
    def parse_workday_type(cls, value):
        if isinstance(value, datetime.time) or isinstance(value, datetime.datetime):
            return WorkerDay.Type.TYPE_WORKDAY.value

        if isinstance(value, str):
            value = value.upper()

            if value == 'В':
                return WorkerDay.Type.TYPE_HOLIDAY.value

            if value == 'ОТ':
                return WorkerDay.Type.TYPE_VACATION.value

            if value == 'ОВ':  # что это?
                return WorkerDay.Type.TYPE_HOLIDAY.value

            if value == 'ОЖ':
                return WorkerDay.Type.TYPE_MATERNITY.value

            cls.parse_work_time(value)
            return WorkerDay.Type.TYPE_WORKDAY.value

        if isinstance(value, float):
            if math.isnan(value):
                return WorkerDay.Type.TYPE_HOLIDAY.value

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_work_time(cls, value):
        if isinstance(value, datetime.time):
            return value

        if isinstance(value, datetime.datetime):
            return value.time()

        if isinstance(value, str):
            return datetime.datetime.strptime(value, '%H:%M').time()

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_date(cls, value):
        if isinstance(value, datetime.datetime):
            return value

        if isinstance(value, str):
            return datetime.datetime.strptime(value + '.2018', '%d.%m.%Y').date()

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_cashbox_type_name(cls, value):
        mapping = {
            'инфо': 'Информация',
            'ret': 'Возврат',
            'гк': 'Главная касса',
            'оркк': 'ОРКК',
            'сверка': 'Сверка',
            'сц': 'СЦ',
            'B2B': 'Линия',
            'В2В': 'Линия',  # яхз русский у них язык или англб
            'час': 'Линия',
            'дост': 'Доставка',
            'deli': 'Доставка',
            'queer': None,
            'серв': None,
            'декр': '_декрет',
            'мспок': None,
            'бух': None
        }

        if isinstance(value, str):
            value = value.lower()

        return mapping.get(value, 'Линия')


class DemandParseHelper(object):
    @classmethod
    def parse_time(cls, value):
        h, m = value.split('h')
        return datetime.time(int(h), int(m))

    @classmethod
    def parse_date(cls, value):
        if isinstance(value, datetime.date):
            value += datetime.timedelta(days=364)
            return value

        raise Exception('cannot parse {}'.format(value))

    @classmethod
    def parse_demand(cls, value):
        if math.isnan(value):
            return 0
        return value


def range_i(start, stop=None, step=1):
    if stop is None:
        return range(0, start+1, step)
    else:
        return range(start, stop+1, step)


def parse_users_time_sheet(ctx, data, row_begin, row_end, column_sheet_begin, column_sheet_end, verbose):
    def __print(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    column_fio = SheetIndexHelper.get_column('C')
    row_date = SheetIndexHelper.get_row(3)

    row_begin = SheetIndexHelper.get_row(row_begin)
    row_end = SheetIndexHelper.get_row(row_end)
    column_sheet_begin = SheetIndexHelper.get_column(column_sheet_begin)
    column_sheet_end = SheetIndexHelper.get_column(column_sheet_end)

    user = User.objects.create_user(
        username='cscais001.mag003'.format(ctx.shop.id),
        email='q@q.com',
        password='bestcompany003'
    )
    user.shop = ctx.shop
    user.first_name = 'Елена'
    user.middle_name = ' '
    user.last_name = 'Пивоварова'
    user.save()

    counter = 0
    cashboxes_types = {}
    cashboxes = {}
    for row in range_i(row_begin, row_end):
        counter += 1

        first_name, middle_name, last_name = UserParseHelper.parse_fio(data[column_fio][row])
        user = User.objects.create_user(
            username='u_{}_{}'.format(ctx.shop.id, counter),
            email='q@q.com',
            password='4242'
        )
        user.shop = ctx.shop
        user.work_type = User.WorkType.TYPE_5_2.value
        user.first_name = first_name
        user.middle_name = middle_name
        user.last_name = last_name
        user.save()

        __print('Created user {} {}'.format(user.first_name, user.last_name))

        for col in range_i(column_sheet_begin, column_sheet_end, 3):
            cashbox_type_name = UserParseHelper.parse_cashbox_type_name(data[col + 2][row])
            if cashbox_type_name in cashboxes_types:
                cashbox_type = cashboxes_types[cashbox_type_name]
                cashbox = cashboxes[cashbox_type_name]
            else:
                cashbox_type = CashboxType.objects.create(shop=ctx.shop, name=cashbox_type_name, is_stable=cashbox_type_name in ['Линия', 'Возврат'])
                cashboxes_types[cashbox_type_name] = cashbox_type
                __print('Created cashbox_type {} with name {}'.format(cashbox_type.id, cashbox_type.name))

                cashbox = Cashbox.objects.create(type=cashbox_type, number='1')
                cashboxes[cashbox_type_name] = cashbox
                __print('Created cashbox {} for type {}:{}'.format(cashbox.id, cashbox_type.id, cashbox_type.name))

            dt = UserParseHelper.parse_date(data[col][row_date])
            workday_type = UserParseHelper.parse_workday_type(data[col][row])
            is_wk = workday_type == WorkerDay.Type.TYPE_WORKDAY.value
            tm_work_start = UserParseHelper.parse_work_time(data[col][row]) if is_wk else None
            tm_work_end = UserParseHelper.parse_work_time(data[col + 1][row]) if is_wk else None

            wd = WorkerDay.objects.create(
                worker=user,
                dt=dt,
                type=workday_type,
                worker_shop=ctx.shop,
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

    for user in User.objects.filter(shop=ctx.shop):
        for cashbox_type in cashboxes_types.values():
            WorkerCashboxInfo.objects.create(
                worker=user,
                cashbox_type=cashbox_type
            )


def parse_time_sheet(ctx, data, row_begin, row_end, column_sheet_begin, column_sheet_end, use_one_column):
    def __print(*args, **kwargs):
        if ctx.verbose:
            print(*args, **kwargs)

    column_fio = SheetIndexHelper.get_column('C')
    column_cashbox_type = SheetIndexHelper.get_column('D')
    row_date = SheetIndexHelper.get_row(3)

    row_begin = SheetIndexHelper.get_row(row_begin)
    row_end = SheetIndexHelper.get_row(row_end)
    column_sheet_begin = SheetIndexHelper.get_column(column_sheet_begin)
    column_sheet_end = SheetIndexHelper.get_column(column_sheet_end)

    cashboxes_counter = {}

    counter = 5000
    cashboxes_types = {x.name: x for x in CashboxType.objects.filter(shop_id=ctx.shop.id)}
    cashboxes = {c_name: Cashbox.objects.filter(type=c)[0] for c_name, c in cashboxes_types.items()}
    for row in range_i(row_begin, row_end):
        counter += 1

        first_name, middle_name, last_name = DataParseHelper.parse_fio(data[column_fio][row])
        try:
            user = User.objects.get(first_name=first_name, middle_name=middle_name, last_name=last_name)
        except User.DoesNotExist:
            user = User.objects.create_user(
                username='u_{}_{}'.format(ctx.shop.id, counter),
                email='q@q.com',
                password='4242'
            )
            user.shop = ctx.shop
            user.work_type = User.WorkType.TYPE_5_2.value
            user.first_name = first_name
            user.middle_name = middle_name
            user.last_name = last_name
            user.save()

        __print('Created user {} {}'.format(user.first_name, user.last_name))

        for col in range_i(column_sheet_begin, column_sheet_end, 3):
            one_column_cashbox_type_name = DataParseHelper.parse_cashbox_type_name(data[column_cashbox_type][row])
            cashbox_type_name = DataParseHelper.parse_cashbox_type_name(data[column_cashbox_type if use_one_column else (col+2)][row])

            if cashbox_type_name not in cashboxes_counter:
                cashboxes_counter[cashbox_type_name] = 0
            cashboxes_counter[cashbox_type_name] += 1

            if cashbox_type_name is None:
                continue

            if one_column_cashbox_type_name is None or not one_column_cashbox_type_name.startswith('_'):
                if cashbox_type_name in cashboxes_types:
                    cashbox_type = cashboxes_types[cashbox_type_name]
                    cashbox = cashboxes[cashbox_type_name]
                else:
                    cashbox_type = CashboxType.objects.create(shop=ctx.shop, name=cashbox_type_name, is_stable=cashbox_type_name in ['Линия', 'Возврат'])
                    cashboxes_types[cashbox_type_name] = cashbox_type
                    __print('Created cashbox_type {} with name {}'.format(cashbox_type.id, cashbox_type.name))

                    cashbox = Cashbox.objects.create(type=cashbox_type, number='1')
                    cashboxes[cashbox_type_name] = cashbox
                    __print('Created cashbox {} for type {}:{}'.format(cashbox.id, cashbox_type.id, cashbox_type.name))

                workday_type = DataParseHelper.parse_workday_type(data[col][row])
            else:
                if one_column_cashbox_type_name == '_декрет':
                    workday_type = WorkerDay.Type.TYPE_MATERNITY.value
                else:
                    raise Exception('unknown one_column_cashbox_type_name')

                cashbox = None

            dt = DataParseHelper.parse_date(data[col][row_date])
            is_wk = workday_type == WorkerDay.Type.TYPE_WORKDAY.value
            tm_work_start = DataParseHelper.parse_work_time(data[col][row]) if is_wk else None
            tm_work_end = DataParseHelper.parse_work_time(data[col+1][row]) if is_wk else None

            wd = WorkerDay.objects.create(
                worker=user,
                dt=dt,
                type=workday_type,
                worker_shop=ctx.shop,
                tm_work_start=tm_work_start,
                tm_work_end=tm_work_end
            )

            if is_wk:
                if cashbox is None:
                    raise Exception('cashbox is none')

                wdcd = WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    on_cashbox=cashbox,
                    tm_from=tm_work_start,
                    tm_to=tm_work_end
                )

    print('cc', cashboxes_counter)

    for user in User.objects.filter(shop=ctx.shop):
        for cashbox_type in cashboxes_types.values():
            try:
                WorkerCashboxInfo.objects.get(
                    worker=user,
                    cashbox_type=cashbox_type
                )
            except WorkerCashboxInfo.DoesNotExist:
                WorkerCashboxInfo.objects.create(
                    worker=user,
                    cashbox_type=cashbox_type
                )
            except WorkerCashboxInfo.MultipleObjectsReturned:
                pass


def parse_demand_time_sheet(ctx, data, row_begin, row_end, column_begin, column_end):
    row_begin = SheetIndexHelper.get_row(row_begin)
    row_end = SheetIndexHelper.get_row(row_end)
    column_begin = SheetIndexHelper.get_column(column_begin)
    column_end = SheetIndexHelper.get_column(column_end)

    column_time = SheetIndexHelper.get_column('A')
    row_date = SheetIndexHelper.get_row(2)

    cashbox_type = CashboxType.objects.get(
        shop=ctx.shop,
        name='Линия'
    )

    for col in range_i(column_begin, column_end):
        dt = DemandParseHelper.parse_date(data[col][row_date])
        for row in range_i(row_begin, row_end, 2):
            tm = DemandParseHelper.parse_time(data[column_time][row])
            value = DemandParseHelper.parse_demand(data[col][row]) + DemandParseHelper.parse_demand(data[col][row+1])
            PeriodDemand.objects.create(
                dttm_forecast=datetime.datetime.combine(dt, tm),
                clients=value,
                products=0,
                type=PeriodDemand.Type.LONG_FORECAST.value,
                cashbox_type=cashbox_type,
                queue_wait_time=random.randint(1, 9),
                queue_wait_length=random.randint(1, 5),
            )


def run(path, super_shop):
    verbose = False

    def __print(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)

    ctx = Context()
    ctx.shop = Shop.objects.create(super_shop=super_shop, title='Кассиры', hidden_title='common')
    __print('Created shop {} with title {}'.format(ctx.shop.id, ctx.shop.title))
    ctx.verbose = False

    users_path = os.path.join(path, 'users.xlsx')
    data = pandas.read_excel(users_path, 'График', header=None)

    parse_users_time_sheet(
        ctx=ctx,
        data=data,
        row_begin=6,
        row_end=88,
        column_sheet_begin='G',
        column_sheet_end='CP',
        verbose=verbose
    )

    data = pandas.read_excel(users_path, 'Расчет КК', header=None)
    parse_demand_time_sheet(
        ctx=ctx,
        data=data,
        row_begin=3,
        row_end=72,
        column_begin='B',
        column_end='AE'
    )

    data = pandas.read_excel(os.path.join(path, 'users_m05.xlsx'), 'Лист1', header=None)
    parse_time_sheet(
        ctx=ctx,
        data=data,
        row_begin=6,
        row_end=86,
        column_sheet_begin='G',
        column_sheet_end='CS',
        use_one_column=False
    )

    for user in User.objects.filter(shop_id=ctx.shop.id):
        dttm_from = datetime.datetime(year=1971, month=1, day=1)
        dttm_to = datetime.datetime(year=1971, month=1, day=1, hour=7)
        dttm_step = datetime.timedelta(minutes=30)
        for i in range(7):
            for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
                WorkerConstraint.objects.create(worker=user, weekday=i, tm=dttm.time())
