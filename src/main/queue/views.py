from datetime import timedelta, datetime, time

from src.db.models import (
    WaitTimeInfo,
    PeriodQueues,
    CashboxType,
    Shop,
    PeriodDemand,
    Notifications,
    User,

)
from src.util.models_converter import BaseConverter
from src.util.forms import FormUtil
from src.util.utils import api_method, JsonResponse, outer_server
from .forms import (
    GetTimeDistributionForm,
    GetIndicatorsForm,
    GetParametersForm,
    SetParametersForm,
    ProcessForecastForm,
)


@api_method('GET', GetIndicatorsForm)
def get_indicators(request, form):
    """
    Получить данные по очереди

    Args:
        method: GET
        url: /api/queue/get_indicators
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        type(str): required = True (L/S/F)
        shop_id(int): required = False

    Returns:
        {
            | 'mean_length_usual': float or None,
            | 'mean_wait_time_usual': float or None,
            | 'dead_time_part_usual': float or None
        }

    Raises:
        JsonResponse.internal_error: если нет типов касс с is_main_type = True, либо с именем == 'Возврат'

    """
    dt_from = form['from_dt']
    dt_to = form['to_dt']

    forecast_type = form['type']

    shop_id = FormUtil.get_shop_id(request, form)

    try:
        linear_cashbox_type = CashboxType.objects.get(shop_id=shop_id, is_main_type=True)
    except:
        return JsonResponse.internal_error('Cannot get linear cashbox')

    period_queues = PeriodQueues.objects.filter(
        cashbox_type_id=linear_cashbox_type.id,
        type=forecast_type,
        dttm_forecast__gte=datetime.combine(dt_from, time()),
        dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1)
    )

    queue_wait_length = 0
    for x in period_queues:
        queue_wait_length += x.value

    mean_length_usual = queue_wait_length / len(period_queues) if len(period_queues) > 0 else None
    mean_wait_time_usual = None
    dead_time_part_usual = None

    return JsonResponse.success({
        'mean_length_usual': mean_length_usual,
        'mean_wait_time_usual': mean_wait_time_usual,
        'dead_time_part_usual': dead_time_part_usual,
    })


@api_method('GET', GetTimeDistributionForm)
def get_time_distribution(request, form):
    """
    Args:
        method: GET
        url: /api/queue/get_time_distribution
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        cashbox_type_ids(list): required = True (либо [] -- для всех типов касс)
        shop_id(int): required = False

    Todo:
        Сделать описание. Непонятно что делает функция
    """
    cashbox_type_ids = form['cashbox_type_ids']

    shop_id = form['shop_id']

    wait_time_info = WaitTimeInfo.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt']
    )

    def __add(__dict, __key, __default):
        if __key not in __dict:
            __dict[__key] = __default
        return __dict[__key]

    tmp = {}
    for x in wait_time_info:
        el = __add(tmp, x.cashbox_type_id, {})
        el = __add(el, x.type, {})
        el = __add(el, x.dt, [])
        el.append(x)
    wait_time_info = tmp

    cashboxes_types = CashboxType.objects.filter(shop_id=shop_id)
    if len(cashbox_type_ids) > 0:
        cashboxes_types = [x for x in cashboxes_types if x.id in cashbox_type_ids]

    result = {}
    for cashbox_type in cashboxes_types:
        result[cashbox_type.id] = {}

        for forecast_type in PeriodDemand.FORECAST_TYPES:
            arr = []
            for i in range(1, 10):
                arr.append({
                    'wait_time': i,
                    'proportion': int(30 * (1 - (i-1)/10))
                })
            result[cashbox_type.id][forecast_type[0]] = arr

    return JsonResponse.success(result)


@api_method(
    'GET',
    GetParametersForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def get_parameters(request, form):
    """
    Возвращает параметры по очереди для указанного магазина

    Args:
        method: GET
        url: /api/queue/get_parameters
        shop_id(int): required = False

    Returns:
        {
            | 'mean_queue_length': float,
            | 'max_queue_length': float,
            | 'dead_time_part': float
        }
    """
    shop = Shop.objects.get(id=FormUtil.get_shop_id(request, form))

    return JsonResponse.success({
        'mean_queue_length': shop.mean_queue_length,
        'max_queue_length': shop.max_queue_length,
        'dead_time_part': shop.dead_time_part
    })


@api_method(
    'POST',
    SetParametersForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def set_parameters(request, form):
    """
        Задает параметры для магазина

        Args:
            method: GET
            url: /api/queue/get_parameters
            shop_id(int): required = True
            mean_queue_length(float): required = True
            max_queue_length(float): required = True
            dead_time_part(float): required = True

        Returns:
            {
                | 'mean_queue_length': float,
                | 'max_queue_length': float,
                | 'dead_time_part': float
            }
    """
    shop = Shop.objects.get(id=FormUtil.get_shop_id(request, form))

    shop.mean_queue_length = form['mean_queue_length']
    shop.max_queue_length = form['max_queue_length']
    shop.dead_time_part = form['dead_time_part']
    shop.save()

    return JsonResponse.success({
        'mean_queue_length': shop.mean_queue_length,
        'max_queue_length': shop.max_queue_length,
        'dead_time_part': shop.dead_time_part
    })


@api_method(
    'POST',
    ProcessForecastForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def process_forecast(request, form):
    """

    Args:
         method: POST
         url: /api/queue/process_forecast
         shop_id(int): required = True
    Returns:
        None
    """

    

    return JsonResponse.success()


@outer_server(is_camera=False, decode_body=False)
def set_predict_queue(request, data):
    """
    ждет request'a от qos_algo. когда получает, записывает данные из data в базу данных

    Args:
        method: POST
        url: /api/queue/set_predict_queue
        data(dict):  data от qos_algo
        key(str): ключ
    """
    # уведомляшки всем

    models_list = []

    def save_models(lst, model):
        commit = False
        if model:
            lst.append(model)
            if len(lst) > 1000:
                commit = True
        else:
            commit = True

        if commit:
            PeriodQueues.objects.bulk_create(lst)
            lst[:] = []

    shop = Shop.objects.get(id=data['shop_id'])
    dt_from = BaseConverter.parse_date(data['dt_from'])
    dt_to = BaseConverter.parse_date(data['dt_to'])

    PeriodQueues.objects.filter(
        type=PeriodQueues.LONG_FORECASE_TYPE,
        dttm_forecast__date__gte=dt_from,
        dttm_forecast__date__lte=dt_to,
        cashbox_type__shop_id=shop.id,
    ).delete()

    for period_demand_value in data['demand']:
        clients = period_demand_value['value']
        clients = 0 if clients < 0 else clients
        save_models(
            models_list,
            PeriodQueues(
                type=PeriodQueues.LONG_FORECASE_TYPE,
                dttm_forecast=BaseConverter.parse_datetime(period_demand_value['dttm']),
                cashbox_type_id=period_demand_value['work_type'],
                value=clients,
            )
        )

    save_models(models_list, None)

    # уведомляшки всем
    for u in User.objects.filter(shop=shop, group__in=User.__except_cashiers__):
        Notifications.objects.create(
            type=Notifications.TYPE_SUCCESS,
            to_worker=u,
            text='Был составлен новый прогноз очереди на период с {} по {}'.format(data['dt_from'], data['dt_to'])
        )

    return JsonResponse.success()