from datetime import timedelta, datetime, time

from src.db.models import (
    WaitTimeInfo,
    PeriodQueue,
    CashboxType,
    Shop,
    PeriodDemand
)
from src.util.forms import FormUtil
from src.util.utils import api_method, JsonResponse
from .forms import (
    GetTimeDistributionForm,
    GetIndicatorsForm,
    GetParametersForm,
    SetParametersForm,
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

    period_queues = PeriodQueue.objects.filter(
        cashbox_type_id=linear_cashbox_type.id,
        type=forecast_type,
        dttm_forecast__gte=datetime.combine(dt_from, time()),
        dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1)
    )

    queue_wait_length = 0
    for x in period_queues:
        queue_wait_length += x.queue_wait_length

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
