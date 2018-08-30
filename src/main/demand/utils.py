import json
import urllib.request

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta
from django.conf import settings
from src.conf.djconfig import QOS_DATETIME_FORMAT

from src.db.models import PeriodDemand, CashboxType, Slot
from src.util.models_converter import BaseConverter
from django.db.models import Sum
from django.core.exceptions import EmptyResultSet, ImproperlyConfigured


def set_param_list(shop_id):
    """
    creates dict for algorithm. Note: only CashboxType HARD type is considered
    :param shop_id:
    :return: {cashbox_type_id: {..params..}, cashbox_type_id: {..params..}, ..}
    """
    params_dict = {}
    for cashbox_type in CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD):
        period_params = json.loads(cashbox_type.period_demand_params)
        # checks
        if len(period_params) == 6:
            for parameter in period_params.values():
                if parameter >= 0:
                    pass
                else:
                    raise ValueError('invalid parameter {} for {}'.format(parameter, cashbox_type.name))
        else:
            raise ValueError('invalid number of params for {}'.format(cashbox_type.name))

        params_dict[cashbox_type.id] = period_params

    return params_dict


def create_predbills_request_function(shop_id, dt=None):
    """
    создает request на qos_algo с параметрами которые указаны в aggregation_dict
    :param shop_id: для какого магаза
    :param dt: с какой даты создавать объекты спроса
    :return:
    """
    if dt is None:
        dt = (PeriodDemand.objects.all().order_by('dttm_forecast').last().dttm_forecast + timedelta(hours=7)).date()
    YEARS_TO_COLLECT = 3  # за последние YEARS_TO_COLLECT года
    from_dt_to_collect = dt - relativedelta(years=YEARS_TO_COLLECT)

    period_demands = PeriodDemand.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=shop_id,
        type=PeriodDemand.Type.FACT.value,
        dttm_forecast__gt=from_dt_to_collect,
        dttm_forecast__lt=dt
    )

    if not period_demands:
        raise EmptyResultSet('There is no period demand objects')

    try:
        param_list = set_param_list(shop_id)
    except ValueError as error_message:
        raise ValueError(error_message)

    aggregation_dict = {
        'IP': settings.HOST_IP,
        'dt': BaseConverter.convert_date(dt),
        'algo_params': param_list,
        'period_demands': [
            {
                'CashType': period_demand.cashbox_type_id,
                'products_amount': 0,
                'positions': 0,
                'bills': period_demand.clients,
                'hours': period_demand.dttm_forecast.hour,
                'period': 0 if period_demand.dttm_forecast.minute < 30 else 1,
                'szDate': BaseConverter.convert_date(period_demand.dttm_forecast.date()),
            } for period_demand in period_demands
        ]
    }

    try:
        data = json.dumps(aggregation_dict).encode('ascii')
        req = urllib.request.Request('http://{}/create_pred_bills'.format(settings.TIMETABLE_IP), data=data, headers={'content-type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            res = response.read().decode('utf-8')
        task_id = json.loads(res).get('task_id', '')
        if task_id is None:
            raise Exception('Error upon creating task')
    except Exception:
        raise ImproperlyConfigured('Error upon creating task')


def set_pred_bills_function(data, key):
    """
    ждет request'a от qos_algo. когда получает, записывает данные из data в базу данных
    :param data: json data от qos_algo
    :param key: ключ
    :return:
    """
    if settings.QOS_SET_TIMETABLE_KEY is None:
        return SystemError('key is not configured')
    if key != settings.QOS_SET_TIMETABLE_KEY:
        return SystemError('invalid key')
    try:
        data = json.loads(data)
    except ValueError as ve:
        return ve

    # костыль, но по-другому никак. берем первый пришедший cashbox_type_id и находим для какого магаза составлялся спрос
    shop = CashboxType.objects.get(id=list(data.values())[0]['CashType']).shop
    sloted_cashbox_types = CashboxType.objects.filter(do_forecast=CashboxType.FORECAST_LITE, shop=shop)
    LONG_FORECAST = PeriodDemand.Type.LONG_FORECAST.value

    for period_demand_value in data.values():
        clients = period_demand_value['clients']
        if clients < 0:
            clients = 0
        dttm_forecast = datetime.strptime(period_demand_value['datetime'], QOS_DATETIME_FORMAT)
        cashbox_type_id = period_demand_value['CashType']
        PeriodDemand.objects.update_or_create(
            type=LONG_FORECAST,
            dttm_forecast=dttm_forecast,
            cashbox_type_id=cashbox_type_id,
            defaults={
                'clients': clients
            }
        )

        # блок для составления спроса на слотовые типы касс (никак не зависит от data с qos_algo)
        # todo: возможно не лучшее решение размещать этот блок здесь, потому что он зависит от dttm_forecast
        for sloted_cashbox in sloted_cashbox_types:
            workers_needed = Slot.objects.filter(
                cashbox_type=sloted_cashbox,
                tm_start__lte=dttm_forecast.time(),
                tm_end__gte=dttm_forecast.time(),
            ).aggregate(Sum('workers_needed'))['workers_needed__sum']

            if workers_needed is None:
                workers_needed = 0
            try:
                PeriodDemand.objects.update_or_create(
                    type=LONG_FORECAST,
                    dttm_forecast=dttm_forecast,
                    cashbox_type=sloted_cashbox,
                    defaults={
                        'clients': workers_needed
                    }
                )
            except PeriodDemand.MultipleObjectsReturned as exc:
                print(exc)
                raise Exception('error upon creating period demands for sloted types')

