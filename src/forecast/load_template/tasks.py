import requests
import json
from datetime import datetime, date, timedelta
from dateutil.relativedelta import relativedelta
import logging
from abc import ABC, abstractmethod
from typing import Optional

from django.core.serializers.json import DjangoJSONEncoder

from src.celery.celery import app
from src.forecast.models import LoadTemplate
from src.base.models import Shop
from django.conf import settings
from src.forecast.load_template.utils import prepare_load_template_request, apply_load_template

logger = logging.getLogger('forecast_loadtemplate')


class BaseDateTimeProducer(ABC):
    @abstractmethod
    def produce(self, **kwargs) -> datetime:
        ...


class NowDateTimeProducer(BaseDateTimeProducer):

    def produce(self, **kwargs) -> date:
        return date.today()


class MonthOffsetTimeProducer(BaseDateTimeProducer):

    def produce(self, **kwargs) -> date:
        try:
            month_offset =int(kwargs['month_offset'])
        except KeyError:
            raise KeyError(
                'MonthOffsetTimeProducer.produce requires month_offset as int kwarg'
            )
        try:
            day_offset =int(kwargs['day_offset'])
        except KeyError:
            raise KeyError(
                'MonthOffsetTimeProducer.produce requires day_offset as int kwarg'
            )
        out = (date.today() + relativedelta(months=month_offset)).replace(day=1)
        out += timedelta(days=day_offset)
        return  out


class DateTimeProducerFactory:
    @staticmethod
    def get_factory(frmt: str) -> BaseDateTimeProducer:
        if frmt == 'now':
            out = NowDateTimeProducer()
        elif frmt == 'month_start_with_offset':
            out = MonthOffsetTimeProducer()
        else:
            raise KeyError(f'Date time producer of {frmt} is not supported')
        return out


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
                'df_from_kwargs': '{"month_offset": 1, "day_offset": 0}'
            }
        )
        then data will be updated since start of next mont till end of next month
    """
    df_from_kwargs = json.loads(df_from_kwargs)
    df_to_kwargs = json.loads(df_to_kwargs)

    dt_from_factory = DateTimeProducerFactory.get_factory(frmt=dt_from_policy)
    dt_to_factory = DateTimeProducerFactory.get_factory(frmt=dt_to_policy)

    logger.info(f"start calculation at night with start policy {dt_from_policy}")
    logger.info(f"start calculation at night with finish policy {dt_to_policy}")

    dt_from = dt_from_factory.produce(**df_from_kwargs)
    dt_to = dt_to_factory.produce(**df_to_kwargs)

    # dt_to = (dt_from + relativedelta(months=2)).replace(day=1) - timedelta(days=1)
    logger.info(f"start calculation from {dt_from} to {dt_to}")

    if not settings.CALCULATE_LOAD_TEMPLATE:
        logger.info(f"periodic calc disabled")
        return
    templates = LoadTemplate.objects.filter(
        shops__isnull=False,
    ).distinct('id')
    
    for template in templates:
        calculate_shops_load(load_template_id=template.id, dt_from=dt_from, dt_to=dt_to)
