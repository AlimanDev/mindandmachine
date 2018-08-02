from src.db.models import (
    PeriodDemand,
    User
)
from .forms import GetWorkersToExchange
from .utils import *
from src.util.utils import api_method, JsonResponse
from django.db.models import Max

from src.util.collection import group_by
from src.util.models_converter import UserConverter


@api_method('GET', GetWorkersToExchange)
def get_workers_to_exchange(request, form):
    ct_type = form['specialization']
    dttm_exchange = form['dttm']
    shop_id = form['shop_id'] if form['shop_id'] else request.user.shop_id

    day_begin_dttm = datetime.combine(dttm_exchange.date(), time(6, 30))
    day_end_dttm = datetime.combine(dttm_exchange.date() + timedelta(days=1), time(2, 0))

    cashbox_types_hard_dict = group_by(
        CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_HARD).order_by('id'),
        group_key=lambda x: x.id)

    period_demand = PeriodDemand.objects.filter(
        cashbox_type__shop_id=shop_id,
        dttm_forecast__gte=day_begin_dttm,
        dttm_forecast__lte=day_end_dttm,
        type__in=[
            PeriodDemand.Type.LONG_FORECAST.value,
            PeriodDemand.Type.FACT.value,
        ],
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

    edge_ind = 0
    while (edge_ind < len(period_demand)) and (period_demand[edge_ind].type != PeriodDemand.Type.FACT.value):
        edge_ind += 1
    predict_demand = period_demand[:edge_ind]

    users_who_can_work_on_ct = get_users_who_can_work_on_ct_type(ct_type)

    default_function_dict = {'shop_id': shop_id, 'dttm_exchange': dttm_exchange, 'ct_type': ct_type,
                             'predict_demand': predict_demand, 'mean_bills_per_step': mean_bills_per_step,
                             'cashbox_types': cashbox_types_hard_dict, 'users_who_can_work': users_who_can_work_on_ct}

    # print(overworking(default_function_dict))
    result_dict = overworking(default_function_dict)
    # result_dict = from_other_spec(default_function_dict)
    # result_dict.update(day_switch(default_function_dict))
    # result_dict.update(excess_dayoff(default_function_dict))

    for k in result_dict.keys():
        result_dict[k].update({'user_info': UserConverter.convert(User.objects.get(id=k))})

    return JsonResponse.success(result_dict)
