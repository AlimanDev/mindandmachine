import logging
import time as time_in_secs

import requests
from django.conf import settings
from django.db.models import Q
from django.utils.timezone import now

from src.celery.celery import app
from src.integration.mda.integration import MdaIntegrationHelper
from src.timetable.models import (
    WorkerDay,
)

logger = logging.getLogger('mda_integration')


@app.task
def sync_mda_data(threshold_seconds=settings.MDA_SYNC_DEPARTMENTS_THRESHOLD_SECONDS):
    mda = MdaIntegrationHelper(logger=logger)
    mda.sync_orgstruct(threshold_seconds=threshold_seconds)
    mda.sync_users(threshold_seconds=threshold_seconds)


@app.task
def create_mda_user_to_shop_relation(username, shop_code, debug_info=None):
    resp = requests.post(
        url=settings.MDA_PUBLIC_API_HOST + '/api/public/v1/mindandmachine/userToShop/',
        json={'login': username, 'sap': shop_code},
        headers={'x-public-token': settings.MDA_PUBLIC_API_AUTH_TOKEN},
        timeout=(3, 5),
    )
    try:
        resp.raise_for_status()
    except requests.RequestException:
        logger.exception(f'text:{resp.text}, headers: {resp.headers}, debug_info: {debug_info}')


@app.task
def sync_mda_user_to_shop_relation(dt=None, delay_sec=0.01):
    dt = dt or now().today()
    wdays = WorkerDay.objects.filter(
        Q(is_vacancy=True) | Q(type=WorkerDay.TYPE_QUALIFICATION),
        is_fact=False, is_approved=True,
        shop__isnull=False, employee__isnull=False,
        dt=dt,
    ).values('employee__user__username', 'shop__code').distinct()
    for wd in wdays:
        create_mda_user_to_shop_relation(username=wd['employee__user__username'], shop_code=wd['shop__code'])
        if delay_sec:
            time_in_secs.sleep(delay_sec)
