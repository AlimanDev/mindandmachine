from src.db.models import (
    PeriodDemand,
    WorkerCashboxInfo,
    CashboxType,
    User,
    Shop
)
from datetime import datetime, time, timedelta
from .forms import GetWorkersToExchange
from .utils import (
    get_users_who_can_work_on_ct_type,
    ChangeTypeFunctions,
)
from src.util.utils import api_method, JsonResponse
from django.db.models import Max

from src.util.collection import group_by
from src.util.models_converter import UserConverter


@api_method(
    'GET',
    GetWorkersToExchange,
    lambda_func=lambda x: CashboxType.objects.get(id=x['specialization']).shop
)
def get_workers_to_exchange(request, form):
    ct_type = form['specialization']
    dttm_exchange = form['dttm']
    try:
        shop_id = CashboxType.objects.get(id=ct_type).shop.id
    except Shop.DoesNotExist:
        shop_id = request.user.shop_id

    day_begin_dttm = datetime.combine(dttm_exchange.date(), time(6, 30))
    day_end_dttm = datetime.combine(dttm_exchange.date() + timedelta(days=1), time(2, 0))

    cashbox_types_hard_dict = group_by(
        CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD).order_by('id'),
        group_key=lambda x: x.id
    )

    period_demand = PeriodDemand.objects.filter(
        cashbox_type__shop_id=shop_id,
        dttm_forecast__gte=day_begin_dttm,
        dttm_forecast__lte=day_end_dttm,
        type=PeriodDemand.Type.LONG_FORECAST.value,
        cashbox_type_id__in=list(cashbox_types_hard_dict.keys())
    ).order_by(
        'type',
        'dttm_forecast',
        'cashbox_type_id'
    )

    mean_bills_per_step = WorkerCashboxInfo.objects.filter(
        is_active=True,
        cashbox_type_id__in=list(cashbox_types_hard_dict.keys())
    ).values('cashbox_type_id').annotate(speed_usual=Max('mean_speed'))
    mean_bills_per_step = {m['cashbox_type_id']: m['speed_usual'] for m in mean_bills_per_step}

    predict_demand = period_demand

    users_who_can_work_on_ct = get_users_who_can_work_on_ct_type(ct_type)

    default_function_dict = {
        'shop_id': shop_id,
        'dttm_exchange': dttm_exchange,
        'ct_type': ct_type,
        'predict_demand': predict_demand,
        'mean_bills_per_step': mean_bills_per_step,
        'cashbox_types': cashbox_types_hard_dict,
        'users_who_can_work': users_who_can_work_on_ct
    }

    result_dict = {}
    for f in ChangeTypeFunctions:
        func_result_dict = f(default_function_dict)
        for user_id in func_result_dict:
            if user_id in result_dict.keys():
                if func_result_dict[user_id]['type'] < result_dict[user_id]['type']:
                    result_dict[user_id]['type'] = func_result_dict[user_id]['type']
            else:
                result_dict[user_id] = {}
                result_dict[user_id].update(func_result_dict[user_id])

    for k in result_dict.keys():
        result_dict[k].update({'user_info': UserConverter.convert(User.objects.get(id=k))})

    return JsonResponse.success(result_dict)
