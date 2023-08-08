import json
import uuid
from datetime import date, datetime, timedelta
from typing import Iterable, Union, List

import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError

from celery import group
from src.apps.base.models import Employment, Shop
from src.adapters.celery.celery import app
from src.apps.forecast.models import OperationType, PeriodClients
from src.apps.forecast.period_clients.utils import create_demand
from src.apps.timetable.models import WorkerDay
from src.apps.timetable.work_type.utils import ShopEfficiencyGetter
from src.apps.timetable.worker_day.services.fix import FixWdaysService
from src.apps.timetable.worker_day.utils.utils import create_fact_from_attendance_records
from src.common.jsons import process_single_quote_json
from src.common.time import DateProducerFactory, DateTimeHelper
from src.common.time_series import TIME_FEATURES_ORDERED, produce_dt_feature


@app.task
def clean_wdays(**kwargs):
    return FixWdaysService(**kwargs).run()


@app.task(autoretry_for=(OperationalError,), max_retries=3) # psycopg2.errors.DeadlockDetected is reraised by Django as OperationalError
@transaction.atomic
def recalc_work_hours(*q_objects, **filters) -> int:
    """Recalculate `work_hours` and `dttm_work_start/end_tabel` of `WorkerDays`. `kwargs` - arguments for `filter()`"""
    # TODO: rewrite to in-memory work_hours calculation, save once in bulk_update.
    wdays = WorkerDay.objects.filter(
        *q_objects,
        Q(type__is_dayoff=False) | Q(type__is_dayoff=True, type__is_work_hours=True),
        **filters
    ).order_by(
        'is_fact', 'is_approved'  # plan, then fact
    ).select_related(
        'type',
        'shop__network',
        'shop__settings__breaks',
        'employment__position__breaks',
        'employment__position__network',
        'employee__user__network',
        'closest_plan_approved'
    )
    wd: WorkerDay
    for wd in wdays:
        wd.save(
            recalc_fact=False,
            update_fields=[
                'work_hours',
                'dttm_work_start_tabel',
                'dttm_work_end_tabel',
            ]
        )
    return len(wdays)


@app.task
def recalc_fact_from_records(dt_from=None, dt_to=None, shop_ids=None, employee_days_list=None):
    assert (dt_from and dt_to) or employee_days_list
    if dt_from and type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    if dt_to and type(dt_to) == str:
        dt_to = datetime.strptime(dt_to, settings.QOS_DATETIME_FORMAT).date()
    create_fact_from_attendance_records(
        dt_from=dt_from, dt_to=dt_to, shop_ids=shop_ids, employee_days_list=employee_days_list)


@app.task
def task_set_worker_days_dt_not_actual(dt_fired_changed_employments: List, deleted_employments: List):

    today = datetime.today()

    with transaction.atomic():
        # for employment in created_employments:
        #     WorkerDay.objects_with_excluded.filter(employee_id=employment['employee_id'],
        #                                            dt__gte=employment['dt_fired'],
        #                                            is_vacancy=False)\
        #         .update(dt_not_actual=employment['dt_fired'])
        #
        # for employment in shop_changed_employments:
        #     WorkerDay.objects_with_excluded.filter(employment_id=employment['id'],
        #                                            dt__gt=today,
        #                                            is_vacancy=False)\
        #         .update(dt_not_actual=today + timedelta(1))
        #
        # for employment in position_changed_employments:
        #     WorkerDay.objects_with_excluded.filter(employment_id=employment['id'],
        #                                            dt__gt=today,
        #                                            is_vacancy=False)\
        #         .update(dt_not_actual=today + timedelta(1))

        for employment in dt_fired_changed_employments:
            WorkerDay.objects_with_excluded.filter(employment_id=employment['id'],
                                                   dt_not_actual__isnull=False,
                                                   dt__lt=employment['dt_fired'],
                                                   is_vacancy=False)\
                .update(dt_not_actual=None)

            WorkerDay.objects_with_excluded.filter(employment_id=employment['id'],
                                                   dt__gt=employment['dt_fired'],
                                                   is_vacancy=False)\
                .update(dt_not_actual=employment['dt_fired'])

        for employment in deleted_employments:
            WorkerDay.objects_with_excluded.filter(employment_id=employment['id'],
                                                   is_vacancy=False)\
                .update(dt_not_actual=today)


@app.task
def batch_block_or_unblock(
    dt_from: Union[str, datetime, date] = None,
    dt_to: Union[str, datetime, date] = None,
    is_blocked: bool = True,
    shop_ids: Union[Iterable, None] = None,
    network_id: Union[int, None] = None
    ) -> int:
    """Block/unblock WorkerDays (`is_blocked` field). Returns number of updated days."""
    if dt_from and dt_to:
        # covnert to `date` type
        dt_from = DateTimeHelper.to_dt(dt_from)
        dt_to = DateTimeHelper.to_dt(dt_to)
    else:
        # default to last month
        dt_from, dt_to = DateTimeHelper.last_month_dt_pair()

    q = Q(
        is_blocked=not is_blocked,
        dt__range=(dt_from, dt_to)
    )
    shops = Shop.objects.all()
    if network_id:
        shops = shops.filter(network_id=network_id)
    if shop_ids:
        shops = shops.filter(id__in=shop_ids)
    employees = Employment.objects.get_active(
        dt_from=dt_from,
        dt_to=dt_to,
        shop__in=shops
    ).distinct('employee').values_list('employee', flat=True)
    q &= Q(shop__in=shops) | Q(shop__isnull=True, employee__in=employees)
    wds = WorkerDay.objects.filter(q)
    return wds.update(is_blocked=is_blocked)


def filter_zero_vals(df: pd.DataFrame, level: str) -> pd.DataFrame:
    uniq_id = uuid.uuid4()
    init_cols = df.columns
    if level not in TIME_FEATURES_ORDERED:
        raise KeyError(f'not avaliable to filter data by {level}, only {TIME_FEATURES_ORDERED} supported')
    
    features = []
    for f in TIME_FEATURES_ORDERED:
        new_col = f"{uniq_id}__{f}"
        features.append(new_col)
        df[new_col] = produce_dt_feature(df, col='dttm', feature=f)
        if f == level:
            break

    df = df.assign(drop=df.groupby(features)['value'].transform('sum'))

    df = df[
        df['drop'] > 0
    ]
    return df[init_cols]


@app.task
def get_and_post_efficiency(
        shop_id: int,
        from_dt: Union[str, date],
        to_dt: Union[str, date],
        work_type_id: int,
        op_type: int,
        level_filter: str,
        graph_type: str,
    ) -> None:
    if isinstance(to_dt, str):
        to_dt = datetime.strptime(to_dt, settings.QOS_DATE_FORMAT).date()
    if isinstance(from_dt, str):
        from_dt = datetime.strptime(from_dt, settings.QOS_DATE_FORMAT).date()

    getter = ShopEfficiencyGetter(
        shop_id=shop_id,
        from_dt=from_dt,
        to_dt=to_dt,
        work_type_ids=[work_type_id],
        graph_type=graph_type,
    )
    resp = getter.get()
    to_ext = (
        {
            'dttm': d['dttm'],
            'value': d['amount'],
        }
        for d in resp['tt_periods']['real_cashiers']
    )
    df = pd.DataFrame(to_ext, columns=["dttm", "value"])
    df['dttm'] = pd.to_datetime(df['dttm'])
    df = filter_zero_vals(df, level=level_filter)

    df["timeserie_id"] = op_type
    df["dttm"] = df["dttm"].dt.strftime(settings.QOS_DATETIME_FORMAT)
    if df.shape[0] > 0:
        data = {
            "shop_id": shop_id,
            "dt_from": from_dt,
            "dt_to": to_dt,
            "type": PeriodClients.FACT_TYPE,
            "serie": df.to_dict(orient='records')
        }
        create_demand(data=data)


@app.task
def trigger_import_timetable_to_fpc(
    filter_leaves: str = '1',
    level_filter: str = 'week',
    from_dt_policy: str = 'month_start_with_offset',
    from_dt_kwargs: str = '{"month_offset": -1, "day_offset": 0}',
    to_dt_policy: str = 'month_start_with_offset',
    to_dt_kwargs: str = '{"month_offset": 0, "day_offset": -1}',
    predefined_shops: str = '[]',
    graph_type: str = "fact_approved",
):
    

    from_dt_kwargs_ = process_single_quote_json(s=from_dt_kwargs)
    to_dt_kwargs_ = process_single_quote_json(s=to_dt_kwargs)

    dt_from_factory = DateProducerFactory.get_factory(frmt=from_dt_policy)
    dt_to_factory = DateProducerFactory.get_factory(frmt=to_dt_policy)

    from_dt = dt_from_factory.produce(**from_dt_kwargs_)
    to_dt = dt_to_factory.produce(**to_dt_kwargs_)


    f_ots = (
        OperationType
        .objects
        .select_related('work_type', 'shop')
        .filter(
            (
                Q(shop__dt_closed__isnull=True)
                | Q(shop__dt_closed__gt=from_dt)
            ),
            (
                Q(shop__dttm_deleted__isnull=True)
                | Q(shop__dttm_deleted__gt=from_dt)
            ),
            work_type__isnull=False,
        )
    )
    if int(filter_leaves):
        f_ots = f_ots.exclude(
            shop__id__in=Shop.objects.filter(parent_id__isnull=False).values('parent__id').distinct()
        )
    
    predefined_shops = json.loads(predefined_shops)
    if predefined_shops:
        f_ots = f_ots.filter(shop_id__in=predefined_shops)

    f_ots = f_ots.values("shop_id", "work_type_id", "id")
    tasks_group = group(
        get_and_post_efficiency.s(
            shop_id=obj["shop_id"],
            from_dt=from_dt.strftime(settings.QOS_DATE_FORMAT),
            to_dt=to_dt.strftime(settings.QOS_DATE_FORMAT),
            work_type_id=obj["work_type_id"],
            op_type=obj["id"],
            level_filter=level_filter,
            graph_type=graph_type,
        )
        for obj in f_ots
    )
    tasks_group.apply_async()
