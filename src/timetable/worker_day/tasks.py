from datetime import datetime
from src.timetable.worker_day.utils import create_fact_from_attendance_records
from django.conf import settings
from django.db import transaction

from src.celery.celery import app
from src.timetable.utils import CleanWdaysHelper
from src.timetable.models import WorkerDay


@app.task
def clean_wdays(filter_kwargs: dict = None, exclude_kwargs: dict = None, only_logging=True, clean_plan_empl=False):
    clean_wdays_helper = CleanWdaysHelper(
        filter_kwargs=filter_kwargs,
        exclude_kwargs=exclude_kwargs,
        only_logging=only_logging,
        clean_plan_empl=clean_plan_empl,
    )
    clean_wdays_helper.run()

@app.task
def recalc_wdays(**kwargs):
    wdays_qs = WorkerDay.objects.filter(type__in=WorkerDay.TYPES_WITH_TM_RANGE, **kwargs)
    for wd_id in wdays_qs.values_list('id', flat=True):
        with transaction.atomic():
            wd_obj = WorkerDay.objects.filter(id=wd_id).select_for_update().first()
            if wd_obj:
                wd_obj.save()

@app.task
def recalc_fact_from_records(dt_from, dt_to, shop_ids=None):
    if type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    if type(dt_to) == str:
        dt_to = datetime.strptime(dt_to, settings.QOS_DATETIME_FORMAT).date()
    create_fact_from_attendance_records(dt_from, dt_to, shop_ids=shop_ids)
