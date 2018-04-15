from datetime import timedelta

from src.db.models import WaitTimeInfo, PeriodDemand, CashboxType
from src.util.collection import range_u
from src.util.models_converter import PeriodDemandConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetTimeDistributionForm


@api_method('GET', GetTimeDistributionForm)
def get_time_distribution(request, form):
    cashbox_type_ids = form['cashbox_type_ids']

    shop_id = request.user.shop_id

    dt_from = form['from_dt']
    dt_to = form['to_dt']
    dt_step = timedelta(days=1)

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
            wait_time = 0
            proportion = 0
            count = 0

            for dt in range_u(dt_from, dt_to, dt_step):
                for x in wait_time_info.get(cashbox_type.id, {}).get(forecast_type, {}).get(dt, []):
                    wait_time += x.wait_time
                    proportion += x.proportion
                    count += 1

            result[cashbox_type.id][PeriodDemandConverter.convert_type(forecast_type)] = {
                'wait_time': wait_time / count if count > 0 else 0,
                'proportion': proportion / count if count > 0 else 0
            }

    return JsonResponse.success(result)
