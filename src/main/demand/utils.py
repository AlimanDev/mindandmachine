import json
from urllib import request, error

from datetime import datetime, timedelta
from src.util.utils import JsonResponse
from dateutil.relativedelta import relativedelta
from django.conf import settings

from src.db.models import (
    PeriodClients,
    CashboxType,
    ProductionDay,
    Shop,

)
from src.util.models_converter import BaseConverter, ProductionDayConverter
from django.core.exceptions import EmptyResultSet


# def set_param_list(shop_id):
#     """
#     Создает словарь из типов касс и параметров для них для алгоритма.
#     Здесь же проверяет что все параметры в базе данных заданы правильно.
#
#     Args:
#         shop_id(int): id отдела
#
#     Warning:
#         учитывает только типы касс с do_forecast = CashboxType.FORECAST_HARD
#
#     Returns:
#         {
#             cashbox_type_id: {
#                 | 'max_depth': int,
#                 | 'eta': int,
#                 | 'min_split_loss': int,
#                 | 'reg_lambda': int,
#                 | 'silent': int,
#                 | 'is_main_type': 0/1
#             }, ...
#         }
#     """
#     params_dict = {}
#     # todo: aa: нужно qos_filter_active -- но это треш какой-то, как можно запрогнозировать, если там там по середине
#     # todo: aa: месяца один тип закрылся, а потом новый открылся... трешшшшшш
#
#     for cashbox_type in CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD):
#         params_dict[cashbox_type.id = json.loads(cashbox_type.period_demand_params)
#         # checks
#         if len(period_params) == 6:
#             for parameter in period_params.values():
#                 if parameter >= 0:
#                     pass
#                 else:
#                     raise ValueError('invalid parameter {} for {}'.format(parameter, cashbox_type.name))
#         else:
#             raise ValueError('invalid number of params for {}'.format(cashbox_type.name))
#
#         params_dict[cashbox_type.id] = period_params
#
#     return params_dict


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

    YEARS_TO_COLLECT = 3  # за последние YEARS_TO_COLLECT лет
    predict2days = 62  # на N дней прогноз

    if dt is None:
        dt = datetime.now().date()
        # dt = (PeriodClients.objects.all().order_by('dttm_forecast').last().dttm_forecast).date() + timedelta(days=1)
        # diff_dt = dt_now - dt
        # if  -30 < diff_dt.days < 0:
        #     predict2days += -diff_dt.days

    day_info = ProductionDay.objects.filter(
        dt__gte=dt - relativedelta(years=YEARS_TO_COLLECT),
        dt__lte=dt + timedelta(days=predict2days),
    )

    shop = Shop.objects.select_related('super_shop').filter(id=shop_id).first()

    period_clients = PeriodClients.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=shop_id,
        type=PeriodClients.FACT_TYPE,
        dttm_forecast__date__gt=dt - relativedelta(years=YEARS_TO_COLLECT),
        dttm_forecast__date__lt=dt,
    )

    if not period_clients:
        raise EmptyResultSet('В базе данных нет объектов спроса.')

    try:
        # todo: aa: нужно qos_filter_active -- но это треш какой-то, как можно запрогнозировать, если там там по середине
        # todo: aa: месяца один тип закрылся, а потом новый открылся... трешшшшшш
        work_types_dict = {}
        for cashbox_type in CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD):
            work_types_dict[cashbox_type.id] = {
                'id': cashbox_type.id,
                'predict_demand_params':  json.loads(cashbox_type.period_demand_params),
                'name': cashbox_type.name

            }
    except ValueError as error_message:
        return JsonResponse.internal_error(error_message)

    aggregation_dict = {
        'IP': settings.HOST_IP,
        'algo_params': {
            'days_info': [ProductionDayConverter.convert(day) for day in day_info],
            'dt_from': BaseConverter.convert_date(dt),
            'dt_to': BaseConverter.convert_date(dt + timedelta(days=predict2days)),
            # 'dt_start': BaseConverter.convert_date(dt),
            # 'days': predict2days,
            'period_step': BaseConverter.convert_time(shop.forecast_step_minutes),
            'tm_start': BaseConverter.convert_time(shop.super_shop.tm_start),
            'tm_end': BaseConverter.convert_time(shop.super_shop.tm_end),
        },
        'work_types': work_types_dict,
        'period_demands': [
            {
                'value': period_demand.value,
                'dttm': BaseConverter.convert_datetime(period_demand.dttm_forecast),
                'work_type': period_demand.cashbox_type_id,
            } for period_demand in period_clients
        ],
        'shop_id': shop.id,
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




