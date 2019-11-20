import json
from django.utils import timezone
from django.db.models import F
import pandas as pd
from random import randint
import numpy as np
from datetime import time, datetime
from dateutil.relativedelta import relativedelta
from src.db.models import (
    ExchangeSettings,
    Event,
    Shop,
    User,
    PeriodClients,
    PeriodQueues,
    WorkerDay,
    WorkerConstraint,
    WorkerDayCashboxDetails,
    WorkerCashboxInfo,
    WorkType,
    OperationType,
    Cashbox,
    AttendanceRecords,
    Group,
    FunctionGroup,
    Timetable,
    Notifications,
)
from src.util.models_converter import (
    WorkerDayConverter,
)


def create_shop(shop_id):
    shop = Shop.objects.create(
        parent_id=shop_id,
        title='department №1',
        forecast_step_minutes=time(minute=30),
        break_triplets='[[0, 420, [30]], [420, 600, [30, 30]], [600, 900, [30, 30, 15]]]'
    )
    return shop


def create_timetable(shop_id, dttm):
    tt = Timetable.objects.create(
        status=Timetable.Status.READY.value,
        shop_id=shop_id,
        dt=dttm.date(),
        dttm_status_change=dttm,
        fot=randint(400000, 1000000),
        lack=randint(20, 80),
        idle=randint(20, 40),
        workers_amount=randint(20, 100),
        revenue=randint(700000, 1500000),
        fot_revenue=randint(10, 70)
    )


def create_work_types(work_types, shop):
    wt_dict = {}
    for wt in work_types:
        wt_m = WorkType.objects.create(
            shop=shop,
            name=wt['name'],
            probability=wt['probability'],
            prior_weight=wt['prior_weight']
        )
        OperationType.objects.create(
            name='',
            speed_coef=wt['speed_coef'],
            do_forecast=wt['do_forecast'],
            work_type=wt_m
        )
        wt_dict[wt_m.name] = wt_m
        Cashbox.objects.create(type=wt_m, number=1)
        Cashbox.objects.create(type=wt_m, number=2)
        Cashbox.objects.create(type=wt_m, number=3)
    return wt_dict


def create_forecast(demand: list, work_types_dict: dict, start_dt: timezone.datetime.date, days: int):
    clients_models = []
    queues_models = []

    def add_queues_models(model):
        if model is None:
            create = True
        else:
            queues_models.append(model)
            create = len(queues_models) == 1000

        if create:
            PeriodQueues.objects.bulk_create(queues_models)
            queues_models[:] = []

    def add_clients_models(model):
        if model is None:
            create = True
        else:
            clients_models.append(model)
            create = len(clients_models) == 1000

        if create:
            PeriodClients.objects.bulk_create(clients_models)
            clients_models[:] = []

    dttm_format = '%H:%M:%S %d.%m.%Y'
    df = pd.DataFrame(demand)
    df['dttm_forecast'] = pd.to_datetime(df['dttm_forecast'], format=dttm_format)
    df = df.sort_values('dttm_forecast')

    for wt_key in work_types_dict.keys():
        wt = work_types_dict[wt_key]
        wt_df = df[df['work_type'] == wt_key]
        dt_diff = start_dt - df.iloc[0]['dttm_forecast'].date()
        day = 0
        prev_dt = wt_df.iloc[0]['dttm_forecast'].date()
        wt_df_index = 0
        while day < days:
            item = wt_df.iloc[wt_df_index]
            add_queues_models(PeriodQueues(
                value=item['clients'] * (1 + (np.random.rand() - 0.5) / 5) / 50,
                dttm_forecast=item['dttm_forecast'] + dt_diff,
                type=PeriodQueues.LONG_FORECASE_TYPE,
                operation_type=wt.work_type_reversed.all()[0],
            ))
            add_clients_models(PeriodClients(
                value=item['clients'] * (1 + (np.random.rand() - 0.5) / 10),
                dttm_forecast=item['dttm_forecast'] + dt_diff,
                type=PeriodClients.LONG_FORECASE_TYPE,
                operation_type=wt.work_type_reversed.all()[0],
            ))
            wt_df_index = (wt_df_index + 1) % wt_df.shape[0]
            if prev_dt != item['dttm_forecast'].date():
                day += 1
                prev_dt = item['dttm_forecast'].date()

            if wt_df_index == 0:
                dt_diff = start_dt - wt_df.iloc[0]['dttm_forecast'].date() + timezone.timedelta(days=day + 1)
    add_queues_models(None)
    add_clients_models(None)  # send query to db


def create_users_workdays(workers, work_types_dict, start_dt, days, shop, shop_size, lang='ru'):
    def add_models(lst, model_type, model):
        if model is None:
            create = True
        else:
            lst.append(model)
            create = len(lst) == 1000

        if create:
            model_type.objects.bulk_create(lst)
            lst[:] = []

    dt_format = '%d.%m.%Y'
    tm_format = '%H:%M:%S'

    details = []
    models = []
    models_attendance = []
    infos = [] 
    lang_data = {
        'cashier': 'Кассир',
        'supervisor' : 'Руководитель',
        'f_name' : 'Иван',
        's_name' : 'Иванов'
    }

    if (lang == 'en'):
        lang_data = {
            'cashier': 'Cahier',
            'supervisor' : 'Supervisor',
            'f_name' : 'John',
            's_name' : 'Smith'
        }
        

    cashier_group, created = Group.objects.get_or_create(name=lang_data['cashier'])
    supervisor_group, created = Group.objects.get_or_create(name=lang_data['supervisor'])

    for func in FunctionGroup.FUNCS:
        FunctionGroup.objects.get_or_create(
            access_type=FunctionGroup.TYPE_SUPERSHOP,
            group=supervisor_group,
            func=func,
        )
        if 'get' in func:
            FunctionGroup.objects.get_or_create(
                access_type=FunctionGroup.TYPE_SELF,
                group=cashier_group,
                func=func
            )

    for worker_ind, worker_d in enumerate(workers, start=1):
        if worker_d['general_info']['group'] == 'S':
            worker = User.objects.create_user(
                username='test{}'.format(shop.id),
                email='q@q.com',
                password='test{}'.format(shop.id),
                salary=60000
            )
            worker.first_name = lang_data['f_name']
            worker.last_name = lang_data['s_name']
            worker.function_group = supervisor_group

            worker.shop = shop
            worker.save()
        else:
            worker = User.objects.create(
                username='u_{}_{}'.format(shop.id, worker_ind),
                last_name=worker_d['general_info']['first_name'],
                function_group=cashier_group,
                password='a',
                tabel_code='{}{}'.format(shop.id, worker_ind),
                salary=40000,
                shop=shop,
            )

        WorkerConstraint.objects.bulk_create([
            WorkerConstraint(worker=worker, weekday=wc['weekday'], tm=wc['tm']) for wc in worker_d['constraints_info']
        ])

        for info in worker_d['worker_cashbox_info']:
            add_models(infos, WorkerCashboxInfo, WorkerCashboxInfo(
                worker=worker,
                work_type=work_types_dict[info['work_type']],
                mean_speed=info['mean_speed'],
            ))

        wds = pd.DataFrame(worker_d['workdays'])
        wds['dttm_work_start'] = pd.to_datetime(wds['dttm_work_start'], format=tm_format).dt.time
        wds['dttm_work_end'] = pd.to_datetime(wds['dttm_work_end'], format=tm_format).dt.time
        wds['dt'] = pd.to_datetime(wds['dt'], format=dt_format).dt.date
        wds = wds.sort_values('dt')

        dt_diff = start_dt - wds.iloc[0]['dt']
        day = 0
        day_ind = 0


        while day < days:
            wd = wds.iloc[day_ind]
            dt = wd['dt'] + dt_diff

            default_dttm = timezone.datetime.combine(dt, time(15, 30))
            dttm_work_start = default_dttm if wd['dttm_work_start'] in [pd.NaT, np.NaN] else timezone.datetime.combine(
                dt, wd['dttm_work_start'])
            dttm_work_end = default_dttm if wd['dttm_work_end'] in [pd.NaT, np.NaN] else timezone.datetime.combine(
                dt, wd['dttm_work_end'])
            if dttm_work_start and dttm_work_end and (dttm_work_end < dttm_work_start):
                dttm_work_end += timezone.timedelta(days=1)

            if WorkerDayConverter.parse_type(wd['type']) == WorkerDay.Type.TYPE_WORKDAY.value:
                wd_model = WorkerDay.objects.create(
                    worker=worker,
                    dt=dt,
                    type=WorkerDay.Type.TYPE_WORKDAY.value,

                    dttm_work_start=dttm_work_start,
                    dttm_work_end=dttm_work_end,
                )
                if np.random.randint(3) == 1:
                    wd_model.parent_worker_day = WorkerDay.objects.create(
                        worker=worker,
                        dt=dt,
                        type=WorkerDay.Type.TYPE_HOLIDAY.value,

                        dttm_work_start=None,
                        dttm_work_end=None,
                    )
                    wd_model.created_by=worker
                    wd_model.save()

                if np.random.randint(4) != 1:
                    add_models(details, WorkerDayCashboxDetails, WorkerDayCashboxDetails(
                        worker_day=wd_model,
                        work_type=work_types_dict[wd['work_type']],
                        dttm_from=dttm_work_start,
                        dttm_to=dttm_work_end,
                    ))
                else:
                    add_models(details, WorkerDayCashboxDetails, WorkerDayCashboxDetails(
                        worker_day=wd_model,
                        work_type=work_types_dict[wd['work_type']],
                        dttm_from=dttm_work_start,
                        dttm_to=dttm_work_end,
                        is_vacancy=True,
                    ))
                    if np.random.randint(4) == 1:
                        add_models(details, WorkerDayCashboxDetails, WorkerDayCashboxDetails(
                            work_type=work_types_dict[wd['work_type']],
                            dttm_from=dttm_work_start,
                            dttm_to=dttm_work_end,
                            status=WorkerDayCashboxDetails.TYPE_VACANCY,
                            is_vacancy=True,
                        ))

                add_models(models_attendance, AttendanceRecords, AttendanceRecords(
                    dttm=dttm_work_start,
                    type=AttendanceRecords.TYPE_COMING,
                    user_id=worker.id,
                    shop_id=shop.id,
                ))

                add_models(models_attendance, AttendanceRecords, AttendanceRecords(
                    dttm=dttm_work_end,
                    type=AttendanceRecords.TYPE_LEAVING,
                    user_id=worker.id,
                    shop_id=shop.id,
                ))

            else:
                add_models(models, WorkerDay, WorkerDay(
                    worker=worker,
                    dt=dt,
                    type=WorkerDayConverter.parse_type(wd['type']),

                    dttm_work_start=None if WorkerDayConverter.parse_type(wd['type']) ==
                                            WorkerDay.Type.TYPE_HOLIDAY.value else dttm_work_start,
                    dttm_work_end=None if WorkerDayConverter.parse_type(wd['type']) ==
                                          WorkerDay.Type.TYPE_HOLIDAY.value else dttm_work_end,
                ))
            day += 1
            day_ind = (day_ind + 1) % wds.shape[0]
            if day_ind == 0:
                dt_diff = start_dt - wds.iloc[0]['dt'] + timezone.timedelta(days=day)

    add_models(details, WorkerDayCashboxDetails, None)
    add_models(models, WorkerDay, None)
    add_models(infos, WorkerCashboxInfo, None)
    add_models(models_attendance, AttendanceRecords, None)

    if shop_size in ['small', 'normal']:
        if shop_size == 'small':
            coef = 5
        else:
            coef = 2

        WorkerCashboxInfo.objects.filter(worker__shop=shop).update(mean_speed=F('mean_speed') / coef)
        User.objects.filter(shop=shop).update(dt_fired=timezone.datetime(2018, 1, 1).date())

        for wt_key in work_types_dict.keys():
            wt_type = work_types_dict[wt_key]
            wt_users = list(User.objects.filter(
                workerday__workerdaycashboxdetails__work_type=wt_type,
                shop=shop,
            ).distinct().values_list('id', flat=True))
            wt_users_id = wt_users[:int(len(wt_users) / coef + 0.5)]
            User.objects.filter(id__in=wt_users_id).update(dt_fired=None)

    #  че то как-то не отнормированно получилось все
    WorkerCashboxInfo.objects.all().update(mean_speed=F('mean_speed'))


def create_notifications():
    list_notifications = []
    list_event = []
    for user in User.objects.all():
        list_event.append(Event(
            text='Test notifications',
        ))
        list_notifications.append(Notifications(
            to_worker=user,
            event=list_event[-1],
        ))
    Notifications.objects.bulk_create(list_notifications)
    Event.objects.bulk_create(list_event)


def main(date=None, shops=None, lang='ru', count_of_month=None):
    f_name = 'etc/scripts/test_data.json'

    lang_data = {
        'root_shop': 'Корневой магазин',
        'super_shop': 'Супер Магазин'
    }

    if lang == 'en':
        lang_data = {
            'root_shop': 'Root shop',
            'super_shop': 'Super Shop'
        }
        f_name = 'etc/scripts/test_data_en.json'
    

    f = open(f_name)
    data = json.load(f)
    f.close()
    ExchangeSettings.objects.create()
    if date is None:
        date = timezone.now().date()

    if shops is None:
        shops = ['small', 'normal', 'big']
    day_step = 18
    if count_of_month is not None:
        start_date = (date - timezone.timedelta(days=30*count_of_month)).replace(day=1)
        end_date = (date + timezone.timedelta(days=30)).replace(day=1)
    else:
        if date.day > day_step:
            start_date = date.replace(day=1)
        else:
            start_date = (date - timezone.timedelta(days=day_step)).replace(day=1)
        end_date = (start_date + timezone.timedelta(days=day_step * 4)).replace(day=1)

    predict_date = (end_date + timezone.timedelta(days=day_step * 2)).replace(day=1)
    worker_days = (end_date - start_date).days
    demand_days = (predict_date - start_date).days + 1
    # print(start_date, end_date, predict_date, worker_days, demand_days)

    root_shop = Shop.objects.create(title=lang_data['root_shop'])
    parent_shop1 = Shop.objects.create(title=f'{lang_data["super_shop"]} № 1', parent = root_shop)
    parent_shop2 = Shop.objects.create(title=f'{lang_data["super_shop"]} № 2', parent = root_shop)
    for shop_ind, shop_size in enumerate(shops, start=1):
        shop = create_shop(parent_shop1.id)
        work_types_dict = create_work_types(data['work_types'], shop)
        create_forecast(data['demand'], work_types_dict, start_date, demand_days)
        create_users_workdays(data['cashiers'], work_types_dict, start_date, worker_days, shop, shop_size, lang=lang)
        dttm_curr = datetime.now().replace(day=1)
        dttm_prev = dttm_curr - relativedelta(months=1)
        create_timetable(shop.id, dttm_curr)
        create_timetable(shop.id, dttm_prev)

    dttm_curr = datetime.now().replace(day=1)
    dttm_prev = dttm_curr - relativedelta(months=1)
    create_notifications()
    for shop_ind in range(4, 2000):
        shop = create_shop(parent_shop2.id)
        shop_id = shop.id
        create_timetable(shop_id, dttm_curr)
        create_timetable(shop_id, dttm_prev)
