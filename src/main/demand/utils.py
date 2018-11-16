import json
from urllib import request, error

from datetime import datetime, timedelta
from src.util.utils import test_algo_server_connection, JsonResponse
from dateutil.relativedelta import relativedelta
from django.conf import settings
from src.conf.djconfig import QOS_DATETIME_FORMAT

from src.db.models import (
    PeriodClients,
    CashboxType,
    Slot,
    Notifications,
    User,
)
from src.util.models_converter import BaseConverter
from django.db.models import Sum
from django.core.exceptions import EmptyResultSet, ImproperlyConfigured


def set_param_list(shop_id):
    """
    Создает словарь из типов касс и параметров для них для алгоритма.
    Здесь же проверяет что все параметры в базе данных заданы правильно.

    Args:
        shop_id(int): id отдела

    Warning:
        учитывает только типы касс с do_forecast = CashboxType.FORECAST_HARD

    Returns:
        {
            cashbox_type_id: {
                | 'max_depth': int,
                | 'eta': int,
                | 'min_split_loss': int,
                | 'reg_lambda': int,
                | 'silent': int,
                | 'is_main_type': 0/1
            }, ...
        }
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

    Args:
        shop_id(int):
        dt(datetime.date): дата на которую создавать PeriodDemand'ы

    Returns:
        None

    Raises:
        Exception

    """
    test_result = test_algo_server_connection()

    if test_result is not True:
        return test_result

    if dt is None:
        dt = (PeriodClients.objects.all().order_by('dttm_forecast').last().dttm_forecast + timedelta(hours=7)).date()
    YEARS_TO_COLLECT = 3  # за последние YEARS_TO_COLLECT года
    from_dt_to_collect = dt - relativedelta(years=YEARS_TO_COLLECT)

    period_clients = PeriodClients.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=shop_id,
        type=PeriodClients.FACT_TYPE,
        dttm_forecast__gt=from_dt_to_collect,
        dttm_forecast__lt=dt
    )

    if not period_clients:
        raise EmptyResultSet('В базе данных нет объектов спроса.')

    try:
        param_list = set_param_list(shop_id)
    except ValueError as error_message:
        return JsonResponse.internal_error(error_message)

    aggregation_dict = {
        'IP': settings.HOST_IP,
        'dt': BaseConverter.convert_date(dt),
        'algo_params': param_list,
        'period_demands': [
            {
                'CashType': period_demand.cashbox_type_id,
                'products_amount': 0,
                'positions': 0,
                'bills': period_demand.value,
                'hours': period_demand.dttm_forecast.hour,
                'period': 0 if period_demand.dttm_forecast.minute < 30 else 1,
                'szDate': BaseConverter.convert_date(period_demand.dttm_forecast.date()),
            } for period_demand in period_clients
        ]
    }

    data = json.dumps(aggregation_dict).encode('ascii')
    req = request.Request('http://{}/create_pred_bills'.format(settings.TIMETABLE_IP), data=data, headers={'content-type': 'application/json'})
    try:
        response = request.urlopen(req)
    except request.HTTPError:
        raise JsonResponse.algo_internal_error('Ошибка при чтении ответа от второго сервера.')
    except error.URLError:
        return JsonResponse.algo_internal_error('Сервер для обработки алгоритма недоступен.')
    task_id = json.loads(response.read().decode('utf-8')).get('task_id')
    if task_id is None:
        return JsonResponse.algo_internal_error('Ошибка при создании задачи на исполненение.')
    return True


def set_pred_bills_function(data, key):
    """
    ждет request'a от qos_algo. когда получает, записывает данные из data в базу данных

    Args:
        data(str): json data от qos_algo
        key(str): ключ

    Raises:
        SystemError: если клюс не передан или не соответствует
        ValueError: если ошибка при загрузке data'ы
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

    forecast_from = None
    forecast_to = None

    for period_demand_value in data.values():
        clients = period_demand_value['clients']
        if clients < 0:
            clients = 0
        dttm_forecast = datetime.strptime(period_demand_value['datetime'], QOS_DATETIME_FORMAT)
        if forecast_from is None:
            forecast_from = dttm_forecast.date()
        forecast_to = dttm_forecast.date()
        cashbox_type_id = period_demand_value['CashType']
        PeriodClients.objects.update_or_create(
            type=PeriodClients.LONG_FORECASE_TYPE,
            dttm_forecast=dttm_forecast,
            cashbox_type_id=cashbox_type_id,
            defaults={
                'value': clients
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
                PeriodClients.objects.update_or_create(
                    type=PeriodClients.LONG_FORECASE_TYPE,
                    dttm_forecast=dttm_forecast,
                    cashbox_type=sloted_cashbox,
                    defaults={
                        'value': workers_needed
                    }
                )
            except PeriodClients.MultipleObjectsReturned as exc:
                print('here', exc)
                raise Exception('error upon creating period demands for sloted types')

    for u in User.objects.filter(shop=shop, group=User.__except_cashiers__):
        Notifications.objects.create(
            type=Notifications.TYPE_SUCCESS,
            to_worker=u,
            text='Был составлен новый спрос на период с {} по {}'.format(forecast_from, forecast_to)
        )

