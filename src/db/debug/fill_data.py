import datetime
import os
import random

from django.conf import settings
from django.core.files import File

from src.db import models
from django.utils import timezone


# for load data launch from ./manage.py shell

# todo: use for adding real function from code (not create), which must check unique current values
def add_shops_and_cashboxes(print_loading=True):
    dttm_deleted1 = timezone.now() + timezone.timedelta(days=31)

    # shop 3: kransogorsk
    shop3, _ = models.Shop.objects.get_or_create(
        title='003_test',
        defaults={'beta':0.8},
    )

    cashbox_types_3 = [
        models.CashboxType.objects.get_or_create(shop=shop3, name='Линия (обычные)')[0],
        models.CashboxType.objects.get_or_create(shop=shop3, name='Линия (экспресс)')[0],
        models.CashboxType.objects.get_or_create(shop=shop3, name='Линия (для юрлиц)')[0],
        models.CashboxType.objects.get_or_create(shop=shop3, name='Возврат')[0],
        models.CashboxType.objects.get_or_create(shop=shop3, name='Достака')[0],
        models.CashboxType.objects.get_or_create(shop=shop3, name='Информация')[0],

        models.CashboxType.objects.get_or_create(shop=shop3, name='На улице', dttm_deleted=dttm_deleted1)[0],
    ]

    cash_nums3 = [
        [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        [1, 2, 3, 4, 5, 6, 7, 8, 22, 23],
        [24, 25, 26],
        [28, 29, 30, 31, 32, 33],
        [35, 36],
        # [27, 34],
        [37, 38],
        [40],
    ]

    cashboxes_3 = []
    for j, cash_num_type in enumerate(cash_nums3):
        for i in cash_num_type:
            q, w = models.Cashbox.objects.get_or_create(
                    type=cashbox_types_3[j],
                    number=i,
                    bio='',
            )
            cashboxes_3.append(q)

    if print_loading:
        print('add test shop3')

    dttm_deleted2 = dttm_deleted1 - timezone.timedelta(days=10)
    shop4, _ = models.Shop.objects.get_or_create(
        title='004_test',
        defaults={'mean_queue_length':2},
    )

    cashbox_types_4 = [
        models.CashboxType.objects.get_or_create(shop=shop4, name='Линия (обычные)')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Линия (экспресс)')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Линия (для юрлиц)')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Возврат')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Достака')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Информация')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Выдача')[0],
        models.CashboxType.objects.get_or_create(shop=shop4, name='Крупногабарит')[0],

        models.CashboxType.objects.get_or_create(shop=shop4, name='Краски', dttm_deleted=dttm_deleted2)[0],
    ]

    cash_nums4 = [
        [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 12, 22, 23, 24, 25, 26],
        [11, 13, 14, 15, 16, 17, 18, 19, 20, 21],
        [27, 28, 29],
        [37, 38, 39, 40, 41],
        [43, 44, 45],
        [46, 47],
        [42],
        [32, 33, 34],
        [35],
    ]

    cashboxes_4 = []
    for j, cash_num_type in enumerate(cash_nums4):
        for i in cash_num_type:
            q, w = models.Cashbox.objects.get_or_create(
                type=cashbox_types_4[j],
                number=i,
                bio='',
            )
            cashboxes_4.append(q)

    if print_loading:
        print('add test shop4')
        print('func add_shops_and_cashboxes loaded data')

    return (
        (shop3, cashbox_types_3, cashboxes_3),
        (shop4, cashbox_types_4, cashboxes_4),
    )


def add_users(shop, cashbox_types=None, amount=100, has_special_skill=0.25, print_loading=True):
    """
    add users (workers) for select shop + working types
    :param shop:
    :return:
    """

    first_name = ['Анна', 'Ира', 'Ольга', 'Анастасия', 'МегадлинноеИмяДля']
    last_name = ['Рожкова', 'Цой', 'Пирожкова', 'Рубиникова', 'МегадлиннаяФамилия',]
    birthdays = [
        timezone.datetime(1980, 1, 2).date(),
        timezone.datetime(1990, 3, 5).date(),
        timezone.datetime(1960, 5, 2).date(),
        timezone.datetime(1960, 5, 18).date(),
        timezone.datetime(1960, 1, 2).date(),
    ]

    if cashbox_types is None:
        cashbox_types = models.CashboxType.objects.filter(shop=shop).order_by('id')

    for i in range(amount):
        with open('src/db/debug/avatar.jpg', 'rb') as av_file:
            f, l, b, w = random.randint(0, 4),random.randint(0, 4), random.randint(0, 4), random.randint(1, 5)
            user, _ = models.User.objects.get_or_create(
                username=shop.title + str(i),
                shop=shop,
                defaults={
                    'first_name': first_name[f],
                    'last_name': last_name[l],
                    'birthday': birthdays[b],
                    'work_type': w,
                    'permissions': 1,
                    'avatar': File(av_file, name='avatar')
                }
            )

        t, d = random.randint(0, 1), random.randint(0, 90)
        s, st = random.random(), random.randint(2, len(cashbox_types) - 1)
        models.WorkerCashboxInfo.objects.get_or_create(
            cashbox_type=cashbox_types[t],
            worker=user,
            defaults={
                'mean_speed': random.random() * 3,
                'bills_amount':d * random.random() * 2,
                'period':d
            }
        )
        if s < has_special_skill:
            models.WorkerCashboxInfo.objects.get_or_create(
                cashbox_type=cashbox_types[st],
                worker=user,
                defaults={
                    'mean_speed': random.random() * 4.5,
                    'bills_amount': d * random.random(),
                    'period': d
                }
            )

    if print_loading:
        print('add users and WorkerCashInfo for shop: {}'.format(shop.title))


def add_work_days(shop, cashboxes, dttm_start, dttm_end, work_days, changes=0.2, double_changes=0.1, request_c=0.2, print_loading=True):
    days = (dttm_end - dttm_start).days
    threshold = work_days / days
    not_work_types = [
        models.WorkerDay.Type.TYPE_HOLIDAY.value,
        models.WorkerDay.Type.TYPE_VACATION.value,
        models.WorkerDay.Type.TYPE_SICK.value,
        models.WorkerDay.Type.TYPE_QUALIFICATION.value,
        models.WorkerDay.Type.TYPE_ABSENSE.value,
        models.WorkerDay.Type.TYPE_MATERNITY.value,
    ]
    max_ind = len(not_work_types) - 1

    dttms = [dttm_start + timezone.timedelta(days=i) for i in range(days)]
    users = models.User.objects.filter(shop=shop)

    def __gen_type(__wk):
        return models.WorkerDay.Type.TYPE_WORKDAY.value if __wk else not_work_types[random.randint(0, max_ind)]

    def __gen_tm_work_start(__wk):
        return datetime.time(random.randint(7, 14)) if __wk else None

    def __gen_tm_work_end(__wk):
        return datetime.time(random.randint(13, 21)) if __wk else None

    def __gen_tm_break_start(__wk):
        return datetime.time(random.randint(12, 16)) if __wk else None

    for user in users:
        cur_d = -1
        u_threshold = threshold + (random.random() - 0.5) / 10
        for i in range(days):
            is_wk = random.random() > u_threshold

            st = __gen_type(is_wk)
            tm_work_start = __gen_tm_work_start(is_wk)
            tm_work_end = __gen_tm_work_end(is_wk)
            tm_break_start = __gen_tm_break_start(is_wk)

            wd = models.WorkerDay.objects.create(
                worker=user,
                worker_shop_id=user.shop_id,
                type=st,
                dt=dttms[i],
                tm_work_start=tm_work_start,
                tm_work_end=tm_work_end,
                tm_break_start=tm_break_start
            )

            if is_wk:
                models.WorkerDayCashboxDetails.objects.create(
                    worker_day=wd,
                    on_cashbox=random.choice(cashboxes),
                    tm_from=tm_work_start,
                    tm_to=tm_work_end
                )

            cr = random.random()
            if cr < changes:
                tp = not_work_types[random.randint(0, max_ind)]
                models.WorkerDayChangeLog.objects.create(
                    worker_day=wd,
                    worker_day_dt=wd.dt,
                    worker_day_worker=wd.worker,
                    from_type=tp,
                    to_type=st,
                    to_tm_work_start=tm_work_start,
                    to_tm_work_end=tm_work_end,
                    to_tm_break_start=tm_break_start,
                    changed_by=user, # todo: only main users could do it
                )
                if cr < double_changes:
                    models.WorkerDayChangeLog.objects.create(
                        worker_day=wd,
                        worker_day_dt=wd.dt,
                        worker_day_worker=wd.worker,
                        from_type=not_work_types[random.randint(0, max_ind)],
                        to_type=tp,
                        changed_by=user,  # todo: only main users could do it
                    )
            cr = random.random()
            if cr < request_c:
                models.WorkerDayChangeRequest.objects.create(
                    worker_day=wd,
                    worker_day_dt=wd.dt,
                    worker_day_worker=wd.worker,
                    type=not_work_types[random.randint(0, max_ind)],
                )

    if print_loading:
        print('add add_work_days for shop: {}'.format(shop.title))


def add_constraints(shop, cons_c=0.35, print_loading=True):
    users = models.User.objects.filter(shop=shop)
    cons_amount = 7 * 16 * 2 # days * hours * period in hour

    for user in users:
        u_cons_c = cons_c + (random.random() + 0.5) / 10
        for i in range(int(cons_amount * u_cons_c)):
            d, h, p = random.randint(0, 6), random.randint(7, 23), random.randint(0, 1)
            is_active = random.random() > 0.1
            if is_active:
                models.WorkerConstraint.objects.get_or_create(
                    worker=user,
                    weekday=d,
                    tm=datetime.time(hour=h, minute=p * 30)
                )
    if print_loading:
        print('add constraints for shop: {}'.format(shop.title))


def add_demand(shop, dt_start, dt_end, cashbox_types=None, step=30, changes_c=0.2, print_loading=True):
    days = (dt_end - dt_start).days
    dts = [dt_start + timezone.timedelta(days=i) for i in range(days)]
    steps_in_h = 60 // step
    tms = [datetime.time(hour=7 + i // steps_in_h, minute=step * (i % steps_in_h)) for i in range(17 * steps_in_h)]

    user = models.User.objects.filter(shop=shop).first()
    if cashbox_types is None:
        cashbox_types = models.CashboxType.objects.filter(shop=shop).order_by('id')

    for dt in dts:
        for tm in tms:
            dttm = timezone.datetime.combine(dt, tm).replace(tzinfo=timezone.utc)
            for i, cash_tp in enumerate(cashbox_types[:6]):
                for tp in [models.PeriodDemand.Type.LONG_FORECAST.value, models.PeriodDemand.Type.FACT.value]:
                    pd, _ = models.PeriodDemand.objects.get_or_create(
                        # shop=shop,
                        dttm_forecast=dttm,
                        type=tp,
                        сashbox_type=cash_tp,
                        defaults={
                            'clients': random.randint(10, 200) // (i + 1),
                            'products': random.randint(60, 1200) // (i + 1),

                            'queue_wait_time': 1.1 + random.random() * 2,
                            'queue_wait_length': 1 + random.randint(0, 2),
                        }
                    )
                    if tp == models.PeriodDemand.Type.LONG_FORECAST:
                        c = random.random()
                        if c < changes_c:
                            models.PeriodDemandChangeLog.objects.create(
                                period_demand=pd,
                                changed_by=user,

                                from_amount=random.randint(10, 200) // (i + 1),
                                to_amount=pd.clients,
                            )

    if print_loading:
        print('add demands for shop: {}'.format(shop.title))


class OfficialHolidays(object):
    @classmethod
    def add(cls):
        all_dates = cls.__parse_file()
        for d in all_dates:
            models.OfficialHolidays.objects.create(country='ru', date=d)

    @classmethod
    def __parse_file(cls):
        all_dates = []
        with open('src/db/debug/official_ru_holidays.csv') as f:
            is_header = True
            for l in f:
                if is_header:
                    is_header = False
                    continue

                arr = cls.__parse_str(l)
                all_dates += cls.__prepare_dates(int(arr[0]), arr[1:])

        return all_dates

    @classmethod
    def __parse_str(cls, s):
        result = []
        substr = ''
        is_quote = False
        for c in s:
            if c == '"':
                is_quote = not is_quote
            elif c == ",":
                if is_quote:
                    substr += c
                else:
                    result.append(substr)
                    substr = ''
            else:
                substr += c

        if substr != '':
            result.append(substr)

        # 1 year + 12 months
        return result[:13]

    @classmethod
    def __prepare_dates(cls, year, months):
        month_counter = 0
        all_dates = []
        for month in months:
            month_counter += 1
            days = [int(x) for x in month.split(',') if '*' not in x]
            dates = [datetime.date(year, month_counter, d) for d in days]
            all_dates += dates

        return all_dates


def load_data(print_loading=True):
    if not (isinstance(settings.MEDIA_ROOT, str) and settings.MEDIA_ROOT.endswith('/qos/media/')):
        raise Exception('cannot remove /qos/media/ folder')

    os.system('rm -r {}*'.format(settings.MEDIA_ROOT))

    now = timezone.now()
    dt_from = (now - timezone.timedelta(days=60)).date()
    dt_to = (now + timezone.timedelta(days=60)).date()

    shop3, shop4 = add_shops_and_cashboxes(print_loading=print_loading)

    add_users(shop3[0], shop3[1], print_loading=print_loading)
    add_users(shop4[0], shop4[1], 110, print_loading=print_loading)

    add_work_days(shop3[0], shop3[2], dt_from, dt_to, 40)
    add_work_days(shop4[0], shop4[2], dt_from, dt_to, 40)

    add_constraints(shop3[0])
    add_constraints(shop4[0])

    add_demand(shop3[0], dt_from, dt_to, shop3[1])
    add_demand(shop4[0], dt_from, dt_to, shop4[1])

    OfficialHolidays.add()


def delete_data():
    pass
