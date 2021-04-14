import requests
import json
from datetime import datetime, date, timedelta

from django.core.serializers.json import DjangoJSONEncoder

from src.celery.celery import app
from src.forecast.models import LoadTemplate
from src.base.models import Shop
from django.conf import settings
from src.forecast.load_template.utils import prepare_load_template_request, apply_load_template


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
            response = requests.post(f'http://{settings.TIMETABLE_IP}/calculate_shop_load/', data=data)



@app.task
def apply_load_template_to_shops(load_template_id, dt_from, shop_id=None):
    if type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [Shop.objects.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        apply_load_template(load_template_id, shop.id, dt_from)
    # event = Event.objects.create(
    #     type="load_template_apply",
    #     params={
    #         'name': load_template.name,
    #     },
    #     dttm_valid_to=datetime.now() + timedelta(days=2),
    #     shop=Shop.objects.filter(level=0).first(),
    # )
    # create_notifications_for_event(event.id)


@app.task
def calculate_shop_load_at_night():
    if not settings.CALCULATE_LOAD_TEMPLATE:
        return
    templates = LoadTemplate.objects.filter(
        shops__isnull=False,
    ).distinct('id')
    dt_now = date.today()
    dt_to = (dt_now + relativedelta(months=2)).replace(day=1) - timedelta(days=1)
    for template in templates:
        calculate_shops_load(template.id, dt_now, dt_to)
