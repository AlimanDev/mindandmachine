from typing import Union, Iterable
from datetime import datetime, date

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.db.utils import OperationalError

from src.celery.celery import app
from src.base.models import Employment, Shop
from src.timetable.models import WorkerDay
from src.timetable.utils import CleanWdaysHelper
from src.timetable.worker_day.utils.utils import create_fact_from_attendance_records
from src.util.time import DateTimeHelper

@app.task
def clean_wdays(**kwargs):
    clean_wdays_helper = CleanWdaysHelper(**kwargs)
    clean_wdays_helper.run()


@app.task(autoretry_for=(OperationalError,), max_retries=3) # psycopg2.errors.DeadlockDetected is reraised by Django as OperationalError
@transaction.atomic
def recalc_work_hours(**filters):
    """Recalculate `work_hours` and `dttm_work_start/end_tabel` of `WorkerDays`. `kwargs` - arguments for `filter()`"""
    # TODO: rewrite to in-memory work_hours calculation, save once in bulk_update.
    wdays = WorkerDay.objects.filter(
        Q(type__is_dayoff=False) | Q(type__is_dayoff=True, type__is_work_hours=True),
        **filters
    ).order_by(
        'is_fact', 'is_approved'  # plan, then fact
    ).select_for_update()
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
