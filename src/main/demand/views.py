from datetime import datetime, timedelta, time

from src.db.models import PeriodDemand, WorkerCashboxInfo, WorkerDayCashboxDetails, WorkerDay
from src.util.collection import range_u
from src.util.models_converter import BaseConverter, PeriodDemandConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetForecastForm


@api_method('GET', GetForecastForm)
def get_forecast(request, form):
    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    shop = request.user.shop

    data_types = form['data_type']
    cashbox_type_ids = form['cashbox_type_ids']

    period_demand = PeriodDemand.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop.id
    )

    if len(cashbox_type_ids) > 0:
        period_demand = [x for x in period_demand if x.cashbox_type_id in cashbox_type_ids]

    tmp = {}
    for x in period_demand:
        dt = x.dttm_forecast.date()
        if dt not in tmp:
            tmp[dt] = {}

        tm = x.dttm_forecast.time()
        if tm not in tmp[dt]:
            tmp[dt][tm] = []

        tmp[dt][tm].append(x)
    period_demand = tmp

    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'], time())
    dttm_step = timedelta(minutes=30)

    today = datetime.now().date()

    forecast_periods = {x: [] for x in PeriodDemand.Type.values() if x in data_types}

    for forecast_type, forecast_data in forecast_periods.items():
        for dttm in range_u(dttm_from, dttm_to, dttm_step):
            data = {}
            for x in period_demand.get(dttm.date(), {}).get(dttm.time(), []):
                if x.type != forecast_type:
                    continue

                if len(cashbox_type_ids) > 0 and x.cashbox_type_id not in cashbox_type_ids:
                    continue

                if x.cashbox_type_id not in data:
                    data[x.cashbox_type_id] = {_: 0 for _ in ['c', 'p', 'qt', 'ql']}

                data[x.cashbox_type_id]['c'] += x.clients
                data[x.cashbox_type_id]['p'] += x.products
                data[x.cashbox_type_id]['qt'] += x.queue_wait_time
                data[x.cashbox_type_id]['ql'] += x.queue_wait_length

            forecast_data.append({
                'dttm': BaseConverter.convert_datetime(dttm),
                'data': data
            })

    response = {
        'period_step': 30,
        'forecast_periods': {PeriodDemandConverter.convert_type(k): v for k, v in forecast_periods.items()}
    }

    return JsonResponse.success(response)
