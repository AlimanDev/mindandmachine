from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from src.celery.celery import app
from src.timetable.models import WorkerDay
from src.timetable.utils import CleanWdaysHelper
from src.timetable.worker_day.utils import create_fact_from_attendance_records


@app.task
def clean_wdays(**kwargs):
    clean_wdays_helper = CleanWdaysHelper(**kwargs)
    clean_wdays_helper.run()


@app.task
def recalc_wdays(**kwargs):
    wdays_qs = WorkerDay.objects.filter(Q(type__is_dayoff=False) | Q(type__is_dayoff=True, type__is_work_hours=True), **kwargs)
    for wd_id in wdays_qs.values_list('id', flat=True):
        with transaction.atomic():
            wd_obj = WorkerDay.objects.filter(id=wd_id).select_for_update().first()
            if wd_obj:
                wd_obj.save()


@app.task
def recalc_fact_from_records(dt_from=None, dt_to=None, shop_ids=None, employee_days_list=None):
    assert (dt_from and dt_to) or employee_days_list
    if dt_from and type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    if dt_to and type(dt_to) == str:
        dt_to = datetime.strptime(dt_to, settings.QOS_DATETIME_FORMAT).date()
    create_fact_from_attendance_records(
        dt_from=dt_from, dt_to=dt_to, shop_ids=shop_ids, employee_days_list=employee_days_list)
