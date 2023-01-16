import requests
import json
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import logging

from django.core.serializers.json import DjangoJSONEncoder

from src.celery.celery import app
from src.forecast.models import LoadTemplate
from src.base.models import Shop
from django.conf import settings
from src.forecast.load_template.utils import prepare_load_template_request, apply_load_template

logger = logging.getLogger('forecast_loadtemplate')

@app.task
def calculate_shops_load(load_template_id, dt_from, dt_to, shop_id=None):
    if type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    if type(dt_to) == str:
        dt_to = datetime.strptime(dt_to, settings.QOS_DATETIME_FORMAT).date()
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [load_template.shops.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        data = prepare_load_template_request(load_template_id, shop.id, dt_from, dt_to)
        if not (data is None):
            data = json.dumps(data, cls=DjangoJSONEncoder)
            response = requests.post(
                f'http://{settings.TIMETABLE_IP}/calculate_shop_load/',
                data=data,
                timeout=settings.REQUESTS_TIMEOUTS['algo']
            )


@app.task
def apply_load_template_to_shops(load_template_id, shop_id=None):
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [Shop.objects.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        apply_load_template(load_template_id, shop.id)


@app.task
def calculate_shop_load_at_night(start_time_policy: str = 'now'):
    logger.info(f"start calculation at night with policy {start_time_policy}")

    if start_time_policy == 'now':
        dt_from = date.today()
    elif start_time_policy == 'next_month_start':
        dt_from = (date.today() + relativedelta(months=1)).replace(day=1)
    else:
        raise KeyError(f'got start day policy = {start_time_policy} which is not supported, only ["now", "next_month_start"]')
    
    dt_to = (dt_from + relativedelta(months=2)).replace(day=1) - timedelta(days=1)
    logger.info(f"start calculation from {dt_from} to {dt_to}")

    if not settings.CALCULATE_LOAD_TEMPLATE:
        return
    templates = LoadTemplate.objects.filter(
        shops__isnull=False,
    ).distinct('id')
    
    for template in templates:
        calculate_shops_load(load_template_id=template.id, dt_from=dt_from, dt_to=dt_to)
