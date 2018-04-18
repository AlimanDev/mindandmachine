from datetime import datetime, timedelta, time

from src.db.models import PeriodDemand, WorkerCashboxInfo, WorkerDayCashboxDetails, WorkerDay, PeriodDemandChangeLog
from src.util.collection import range_u
from src.util.models_converter import BaseConverter, PeriodDemandConverter, PeriodDemandChangeLogConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetForecastForm, SetDemandForm, GetIndicatorsForm


@api_method('GET', GetIndicatorsForm)
def get_indicators(request, form):
    dt_from = form['from_dt']
    dt_to = form['to_dt']

    forecast_type = form['type']

    shop_id = request.user.shop_id

    period_demands = PeriodDemand.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type=forecast_type,
        dttm_forecast__gte=datetime.combine(dt_from, time()),
        dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1)
    )

    worker_days = WorkerDay.objects.filter(
        worker_shop_id=shop_id,
        type=WorkerDay.Type.TYPE_WORKDAY.value,
        dt__gte=dt_from,
        dt__lte=dt_to
    )
    workers_count = len(set([x.worker_id for x in worker_days]))

    clients = 0
    products = 0
    for x in period_demands:
        clients += x.clients
        products += x.products

    prev_periods_demands = PeriodDemand.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type=forecast_type,
        dttm_forecast__gte=datetime.combine(dt_from, time()) - timedelta(days=30),
        dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1) - timedelta(days=30)
    )

    prev_clients = 0
    for x in prev_periods_demands:
        prev_clients += x.clients

    growth = 0
    if prev_clients != 0:
        growth = (clients - prev_clients) / prev_clients * 100
        growth = max(growth, 0)

    return JsonResponse.success({
        'mean_bills': clients / workers_count if workers_count > 0 else None,
        'mean_codes': products / workers_count if workers_count > 0 else None,
        'mean_income': None,
        'mean_bill_codes': products / clients if clients > 0 else None,
        'growth': growth,
        'total_people': clients,
        'total_bills': clients,
        'total_codes': products,
        'total_income': None
    })


@api_method('GET', GetForecastForm)
def get_forecast(request, form):
    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    shop = request.user.shop

    # data_types = form['data_type']
    data_types = PeriodDemand.Type.values()
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
    dttm_to = datetime.combine(form['to_dt'], time()) + timedelta(days=1)
    dttm_step = timedelta(minutes=30)

    forecast_periods = {x: [] for x in PeriodDemand.Type.values() if x in data_types}

    for forecast_type, forecast_data in forecast_periods.items():
        for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
            clients = 0
            products = 0
            queue_wait_time = 0
            queue_wait_length = 0

            for x in period_demand.get(dttm.date(), {}).get(dttm.time(), []):
                if x.type != forecast_type:
                    continue

                if len(cashbox_type_ids) > 0 and x.cashbox_type_id not in cashbox_type_ids:
                    continue

                clients += x.clients
                products += x.products
                queue_wait_time += x.queue_wait_time
                queue_wait_length += x.queue_wait_length

            forecast_data.append({
                'dttm': BaseConverter.convert_datetime(dttm),
                'B': clients,
                'C': products,
                'L': queue_wait_length,
                'T': queue_wait_time
            })

    period_demand_change_log = PeriodDemandChangeLog.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop.id
    )

    if len(cashbox_type_ids) > 0:
        period_demand_change_log = [x for x in period_demand_change_log if x.cashbox_type_id in cashbox_type_ids]

    period_demand_change_log = [x for x in period_demand_change_log if dttm_from < x.dttm_to or dttm_to > x.dttm_from]

    response = {
        'period_step': 30,
        'forecast_periods': {PeriodDemandConverter.convert_forecast_type(k): v for k, v in forecast_periods.items()},
        'demand_changes': [PeriodDemandChangeLogConverter.convert(x) for x in period_demand_change_log]
    }

    return JsonResponse.success(response)


@api_method('POST', SetDemandForm)
def set_demand(request, form):
    cashbox_type_ids = form['cashbox_type_ids']

    multiply_coef = form.get('multiply_coef')
    set_value = form.get('set_value')

    dttm_from = form['from_dttm']
    dttm_to = form['to_dttm']

    shop_id = request.user.shop_id

    period_demands = PeriodDemand.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type=PeriodDemand.Type.LONG_FORECAST.value,
        dttm_forecast__gte=dttm_from,
        dttm_forecast__lte=dttm_to
    )

    if len(cashbox_type_ids) > 0:
        period_demands = [x for x in period_demands if period_demands.cashbox_type_id in cashbox_type_ids]

    cashboxes_types = []
    for x in period_demands:
        if multiply_coef is not None:
            x.clients *= multiply_coef
        else:
            x.clients = set_value

        x.save()
        cashboxes_types.append(x.cashbox_type_id)

    for x in cashboxes_types:
        PeriodDemandChangeLog.objects.create(
            dttm_from=dttm_from,
            dttm_to=dttm_to,
            cashbox_type_id=x,
            multiply_coef=multiply_coef,
            set_value=set_value
        )

    return JsonResponse.success()
