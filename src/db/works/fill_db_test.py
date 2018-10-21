import json
from django.utils import timezone
from django.db.models import F
import pandas as pd
import numpy as np
from datetime import time
from ..models import (
    SuperShop,
    Shop,
    User,
    PeriodDemand,
    WorkerDay,
    WorkerConstraint,
    WorkerDayCashboxDetails,
    WorkerCashboxInfo,
    CashboxType,
    Cashbox
)
from src.util.models_converter import (
    WorkerDayConverter,
)


def create_shop(shop_ind):
    supershop = SuperShop.objects.create(
        title='Магазин № {}'.format(shop_ind),
        # hidden_title='Магазин № {}'.format(shop_ind),

    )
    shop = Shop.objects.create(
        super_shop=supershop,
        title='',
        # hidden_title='',
        forecast_step_minutes=time(minute=30),
        break_triplets='[[0, 420, [30]], [420, 600, [30, 30]], [600, 900, [30, 30, 15]]]'
    )
    return supershop, shop


def create_work_types(work_types, shop):
    wt_dict = {}
    for wt in work_types:
        wt = CashboxType.objects.create(
            shop=shop,
            **wt,
        )
        wt_dict[wt.name] = wt
        Cashbox.objects.create(type=wt, number=1)
        Cashbox.objects.create(type=wt, number=2)
        Cashbox.objects.create(type=wt, number=3)
    return wt_dict


def create_forecast(demand: list, work_types_dict: dict, start_dt:timezone.datetime.date, days: int):
    _models = []
    def add_models(model):
        if model is None:
            create = True
        else:
            _models.append(model)
            create = len(_models) == 1000

        if create:
            PeriodDemand.objects.bulk_create(_models)
            _models[:] = []

    dttm_format = '%H:%M:%S %d.%m.%Y'
    df = pd.DataFrame(demand)
    df['dttm_forecast'] = pd.to_datetime(df['dttm_forecast'], format=dttm_format)
    df = df.sort_values('dttm_forecast')

    for wt_key in work_types_dict.keys():
        wt = work_types_dict[wt_key]
        wt_df = df[df['cashbox_type'] == wt_key]
        dt_diff = start_dt - df.iloc[0]['dttm_forecast'].date()
        day = 0
        prev_dt = wt_df.iloc[0]['dttm_forecast'].date()
        wt_df_index = 0
        while day < days:
            item = wt_df.iloc[wt_df_index]
            add_models(PeriodDemand(
                clients=item['clients'] * (1 + (np.random.rand() - 0.5) / 10),
                dttm_forecast=item['dttm_forecast'] + dt_diff,
                type=PeriodDemand.Type.LONG_FORECAST.value,
                cashbox_type=wt,
            ))
            wt_df_index = (wt_df_index + 1) % wt_df.shape[0]
            if prev_dt != item['dttm_forecast'].date():
                day += 1
                prev_dt = item['dttm_forecast'].date()

            if wt_df_index == 0:
                dt_diff = start_dt - wt_df.iloc[0]['dttm_forecast'].date() + timezone.timedelta(days=day + 1)
    add_models(None) # send query to db


def create_users_workdays(workers, work_types_dict, start_dt, days, shop, shop_size):
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
    infos = []

    for worker_ind, worker_d in enumerate(workers, start=1):
        if worker_d['general_info']['group'] == User.GROUP_SUPERVISOR:
            worker = User.objects.create_user(
                username='test{}'.format(shop.id),
                email='q@q.com',
                password='test{}'.format(shop.id)
            )
            worker.first_name = 'Иван'
            worker.last_name = 'Иванов'
            worker.group = User.GROUP_SUPERVISOR
            worker.shop = shop
            worker.save()
        else:
            worker = User.objects.create(
                username='u_{}_{}'.format(shop.id, worker_ind),
                group=User.GROUP_CASHIER,
                first_name=worker_d['general_info']['first_name'],
                password='a',
                tabel_code='{}{}'.format(shop.id, worker_ind),
                shop=shop,
            )

        WorkerConstraint.objects.bulk_create([
            WorkerConstraint(worker=worker, weekday=wc['weekday'], tm=wc['tm']) for wc in worker_d['constraints_info']
        ])

        for info in worker_d['worker_cashbox_info']:
            add_models(infos, WorkerCashboxInfo, WorkerCashboxInfo(
                worker=worker,
                cashbox_type=work_types_dict[info['work_type']],
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
            dttm_work_start = default_dttm if wd['dttm_work_start'] in [pd.NaT, np.NaN] else timezone.datetime.combine(dt, wd['dttm_work_start'])
            dttm_work_end = default_dttm if wd['dttm_work_end'] in [pd.NaT, np.NaN] else timezone.datetime.combine(dt, wd['dttm_work_end'])
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
                add_models(details, WorkerDayCashboxDetails, WorkerDayCashboxDetails(
                    worker_day=wd_model,
                    cashbox_type=work_types_dict[wd['work_type']],
                    dttm_from=dttm_work_start,
                    dttm_to=dttm_work_end,
                ))
            else:
                add_models(models, WorkerDay, WorkerDay(
                    worker=worker,
                    dt=dt,
                    type=WorkerDayConverter.parse_type(wd['type']),

                    dttm_work_start=dttm_work_start,
                    dttm_work_end=dttm_work_end,
                ))
            day += 1
            day_ind = (day_ind + 1) % wds.shape[0]
            if day_ind == 0:
                dt_diff = start_dt - wds.iloc[0]['dt'] + timezone.timedelta(days=day)


    add_models(details, WorkerDayCashboxDetails, None)
    add_models(models, WorkerDay, None)
    add_models(infos, WorkerCashboxInfo, None)

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
                workerday__workerdaycashboxdetails__cashbox_type=wt_type,
                shop=shop,
            ).distinct().values_list('id', flat=True))
            wt_users_id = wt_users[:int(len(wt_users) / coef + 0.5)]
            User.objects.filter(id__in=wt_users_id).update(dt_fired=None)

    #  че то как-то не отнормированно получилось все
    WorkerCashboxInfo.objects.all().update(mean_speed=F('mean_speed') * 1.75)



def main(date=None, shops=None):
    f = open('src/db/works/test_data.json')
    data = json.load(f)
    f.close()

    if date is None:
        date = timezone.now().date()

    if shops is None:
        shops = ['small', 'normal', 'big']

    day_step = 18
    if date.day > day_step:
        start_date = date.replace(day=1)
        end_date = (date + timezone.timedelta(days=day_step * 3)).replace(day=1)
    else:
        start_date = (date - timezone.timedelta(days=day_step)).replace(day=1)
        end_date = (date + timezone.timedelta(days=day_step)).replace(day=1)
    predict_date = (end_date + timezone.timedelta(days=day_step * 3)).replace(day=1)
    worker_days = (end_date - start_date).days + 1
    demand_days = (predict_date - start_date).days + 1
    # print(start_date, end_date, predict_date, worker_days, demand_days)

    for shop_ind, shop_size in enumerate(shops, start=1):
        supershop, shop = create_shop(shop_ind)
        work_types_dict = create_work_types(data['cashbox_types'], shop)
        create_forecast(data['demand'], work_types_dict, start_date, demand_days)
        create_users_workdays(data['cashiers'], work_types_dict, start_date, worker_days, shop, shop_size)
