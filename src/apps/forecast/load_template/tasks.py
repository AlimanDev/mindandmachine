import json
import logging
from datetime import datetime
from http import HTTPStatus

import requests
from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder

from src.apps.base.models import Shop
from src.adapters.celery.celery import app
from src.apps.forecast.load_template.utils import (
    apply_load_template,
    prepare_load_template_request,
)
from src.apps.forecast.models import LoadTemplate
from src.common.jsons import process_single_quote_json
from src.common.time import DateProducerFactory

logger = logging.getLogger('forecast_loadtemplate')


def set_shop_lt_status(shop_id: int, status: str):
    shop = Shop.objects.get(id=shop_id)
    shop.load_template_status = status
    shop.save()


@app.task
def calculate_shops_load(load_template_id, dt_from, dt_to, shop_id=None):
    if type(dt_from) == str:
        dt_from = datetime.strptime(dt_from, settings.QOS_DATETIME_FORMAT).date()
    if type(dt_to) == str:
        dt_to = datetime.strptime(dt_to, settings.QOS_DATETIME_FORMAT).date()
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [load_template.shops.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        # set status to disable triggering this shop again
        if shop.load_template_status == Shop.LOAD_TEMPLATE_PROCESS:
            continue
        set_shop_lt_status(shop_id=shop.id, status=Shop.LOAD_TEMPLATE_PROCESS)
        data = prepare_load_template_request(
            load_template_id,
            shop.id,
            dt_from,
            dt_to,
        )
        if not (data is None):
            data = json.dumps(data, cls=DjangoJSONEncoder)
            response = requests.post(
                f'http://{settings.TIMETABLE_IP}/calculate_shop_load/',
                data=data,
                timeout=settings.REQUESTS_TIMEOUTS['algo']
            )

            # if for some reason (validation error) the request is not ok
            # set status to Shop.LOAD_TEMPLATE_ERROR
            if response.status_code != HTTPStatus.OK:
                set_shop_lt_status(shop_id=shop.id, status=Shop.LOAD_TEMPLATE_ERROR)





@app.task
def apply_load_template_to_shops(load_template_id, shop_id=None):
    load_template = LoadTemplate.objects.get(pk=load_template_id)
    shops = [Shop.objects.get(pk=shop_id)] if shop_id else load_template.shops.all()
    for shop in shops:
        apply_load_template(load_template_id, shop.id)


@app.task
def calculate_shop_load_at_night(
    dt_from_policy: str = 'now',
    df_from_kwargs: str = '{}',
    dt_to_policy: str = 'month_start_with_offset',
    df_to_kwargs: str = '{"month_offset": 2, "day_offset": -1}',
):
    """ To start prediction for all load templates
    
    Args:
        dt_from_policy (str): factory key for start date creation
            avaliable: "now", "month_start_with_offset"
        df_from_kwargs (str): json string of kwargs for policy
        dt_to_policy (str): factory key for start date creation
            avaliable: "now", "month_start_with_offset"
        df_from_kwargs (str): json string of kwargs for policy

    Example:
        # 1
        if run with no args then calculation will be done since today till end of next month
        # 2
        # calculate_shop_load_at_night.apply(
            kwargs={
                'dt_from_policy': 'month_start_with_offset',
                'df_from_kwargs': '{"month_offset": 1, "day_offset": 0}',
                'dt_to_policy': 'month_start_with_offset',
                'df_to_kwargs': str = '{"month_offset": 2, "day_offset": -1}',
            }
        )
        then data will be updated since start of next mont till end of next month
    """

    if not settings.CALCULATE_LOAD_TEMPLATE:
        raise ValueError(f"periodic calc disabled")
    
    for policy, kwgrgs, annot in (
        (dt_from_policy, df_from_kwargs, 'from',),
        (dt_to_policy, df_to_kwargs, 'to',),
    ):
        logger.info(
            " ".join(
                [
                    f"start calculation at night with {annot}",
                    f"policy {policy!r} and kwargs {kwgrgs!r}",
                ]
            ),
        )
    _annotation = 'from'
    try:
        _kwrgs = df_from_kwargs
        df_from_kwargs = process_single_quote_json(_kwrgs)
        _annotation = 'to'
        _kwrgs = df_to_kwargs
        df_to_kwargs = process_single_quote_json(s=df_to_kwargs)
    except Exception as e:
        msg = f"wasnt able to create {_annotation} json from {_kwrgs!r}"
        logger.exception(msg)
        raise TypeError(msg) from e

    dt_from_factory = DateProducerFactory.get_factory(frmt=dt_from_policy)
    dt_to_factory = DateProducerFactory.get_factory(frmt=dt_to_policy)

    dt_from = dt_from_factory.produce(**df_from_kwargs)
    dt_to = dt_to_factory.produce(**df_to_kwargs)

    logger.info(f"start calculation from {dt_from} to {dt_to}")

    templates = LoadTemplate.objects.filter(
        shops__isnull=False,
    ).distinct('id')
    
    for template in templates:
        calculate_shops_load(load_template_id=template.id, dt_from=dt_from, dt_to=dt_to)
