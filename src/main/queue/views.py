from datetime import timedelta, datetime, time

from src.db.models import (
    WaitTimeInfo,
    PeriodDemand,
    CashboxType,
    Shop,
    User
)
from src.util.collection import range_u
from src.util.forms import FormUtil
from src.util.models_converter import PeriodDemandConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetTimeDistributionForm, GetIndicatorsForm, GetParametersForm, SetParametersForm


@api_method(
    'GET',
    GetIndicatorsForm,
    groups=User.__except_cashiers__,
    lambda_func=lambda x: Shop.objects.filter(id=x['shop_id']).first()
)
def get_indicators(request, form):
    dt_from = form['from_dt']
    dt_to = form['to_dt']

    forecast_type = form['type']

    shop_id = FormUtil.get_shop_id(request, form)

    try:
        linear_cashbox_type = CashboxType.objects.get(shop_id=shop_id, is_main_type=True)
    except:
        return JsonResponse.internal_error('Cannot get linear cashbox')

    period_demands = list(
        PeriodDemand.objects.filter(
            cashbox_type_id=linear_cashbox_type.id,
            type=forecast_type,
            dttm_forecast__gte=datetime.combine(dt_from, time()),
            dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1)
        )
    )

    queue_wait_time = 0
    queue_wait_length = 0
    for x in period_demands:
        queue_wait_time += x.queue_wait_time
        queue_wait_length += x.queue_wait_length

    mean_length_usual = queue_wait_length / len(period_demands) if len(period_demands) > 0 else None
    mean_wait_time_usual = queue_wait_time / len(period_demands) if len(period_demands) > 0 else None
    dead_time_part_usual = None

    try:
        return_cashbox_type = CashboxType.objects.get(shop_id=shop_id, name='Возврат')
    except:
        return JsonResponse.internal_error('Cannot get return cashbox')

    period_demands = list(
        PeriodDemand.objects.filter(
            cashbox_type_id=return_cashbox_type.id,
            type=forecast_type,
            dttm_forecast__gte=datetime.combine(dt_from, time()),
            dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1)
        )
    )

    queue_wait_time = 0
    queue_wait_length = 0
    for x in period_demands:
        queue_wait_time += x.queue_wait_time
        queue_wait_length += x.queue_wait_length

    mean_length_return = queue_wait_length / len(period_demands) if len(period_demands) > 0 else None
    mean_wait_time_return = queue_wait_time / len(period_demands) if len(period_demands) > 0 else None
    dead_time_part_return = None

    return JsonResponse.success({
        'mean_length_usual': mean_length_usual,
        'mean_wait_time_usual': mean_wait_time_usual,
        'dead_time_part_usual': dead_time_part_usual,
        'mean_length_return': mean_length_return,
        'mean_wait_time_return': mean_wait_time_return,
        'dead_time_part_return': dead_time_part_return,
        'fund': None
    })


@api_method(
    'GET',
    GetTimeDistributionForm,
    groups=User.__except_cashiers__,
    lambda_func=lambda x: Shop.objects.filter(id=x['shop_id']).first()
)
def get_time_distribution(request, form):
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

        for forecast_type in PeriodDemand.Type.values():
            arr = []
            for i in range(1, 10):
                arr.append({
                    'wait_time': i,
                    'proportion': int(30 * (1 - (i-1)/10))
                })
            result[cashbox_type.id][PeriodDemandConverter.convert_forecast_type(forecast_type)] = arr

    return JsonResponse.success(result)


@api_method(
    'GET',
    GetParametersForm,
    groups=User.__except_cashiers__,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def get_parameters(request, form):
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
