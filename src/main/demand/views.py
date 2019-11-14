from datetime import datetime, timedelta, time, date

from src.db.models import (
    Employment,
    PeriodClients,
    PeriodProducts,
    PeriodQueues,
    WorkType,
    PeriodDemandChangeLog,
    Shop,
    Event,
    User,
    FunctionGroup,
    OperationType,
)
from dateutil.relativedelta import relativedelta
from django.db.models import Sum
from src.util.collection import range_u
from src.util.models_converter import BaseConverter, PeriodDemandChangeLogConverter
from src.util.utils import api_method, JsonResponse, outer_server
from .forms import (
    GetForecastForm,
    SetDemandForm,
    GetIndicatorsForm,
    CreatePredictBillsRequestForm,
    GetDemandChangeLogsForm,
    GetVisitorsInfoForm,
    SetPredictBillsForm,
)
from .utils import create_predbills_request_function
from django.apps import apps
import json


@api_method('GET', GetIndicatorsForm)
def get_indicators(request, form):
    """

    Args:
        method: GET
        url: /api/demand/get_indicators
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        work_type_id(int): required = False
        shop_id(int): required = True

    Returns:
        {
            | 'overall_operations': int or None,
            | 'overall_growth': int or None,
            | 'fact_overall_operations': int or None,
        }

    """
    dt_from = form['from_dt']
    dt_to = form['to_dt']
    shop_id = form['shop_id']
    work_type_id = form.get('work_type_id')

    if not work_type_id:
        # work_type_filter_list = WorkType.objects.qos_filter_active(dt_from, dt_to).values_list('id', flat=True)
        work_type_filter_list = WorkType.objects.values_list('id', flat=True)
    else:
        work_type_filter_list = [work_type_id]
    # if not len(work_type_filter_list):
    #     return JsonResponse.internal_error('Нет активных касс в данный период')

    period_filter_dict = {
        'operation_type__work_type__shop_id': shop_id,
        'operation_type__work_type_id__in': work_type_filter_list,
        'dttm_forecast__gte': datetime.combine(dt_from, time()),
        'dttm_forecast__lt': datetime.combine(dt_to, time()) + timedelta(days=1)
    }
    clients = PeriodClients.objects.select_related(
        'operation_type',
        'operation_type__work_type'
    ).filter(**period_filter_dict)
    long_type_clients = clients.filter(type=PeriodClients.LONG_FORECASE_TYPE).aggregate(Sum('value'))['value__sum']
    fact_type_clients = clients.filter(type=PeriodClients.FACT_TYPE).aggregate(Sum('value'))['value__sum']

    prev_clients = PeriodClients.objects.select_related(
        'operation_type__work_type'
    ).filter(
        operation_type__work_type__shop_id=shop_id,
        operation_type__work_type_id__in=work_type_filter_list,
        dttm_forecast__gte=datetime.combine(dt_from, time()) - relativedelta(months=1),
        dttm_forecast__lt=datetime.combine(dt_to, time()) - relativedelta(months=1),
        type=PeriodClients.LONG_FORECASE_TYPE,
    ).aggregate(Sum('value'))['value__sum']

    if long_type_clients and prev_clients and prev_clients != 0:
        growth = (long_type_clients - prev_clients) / prev_clients * 100
    else:
        growth = None

    return JsonResponse.success({
        'overall_operations': long_type_clients / 1000 if long_type_clients else None,  # в тысячах
        'operations_growth': growth,
        'fact_overall_operations': fact_type_clients / 1000 if fact_type_clients else None,
    })


@api_method('GET', GetForecastForm)
def get_forecast(request, form):
    """
    Получаем прогноз

    Args:
        method: GET
        url: /api/demand/get_forecast
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        operation_type_ids(list): список типов касс (либо [] -- для всех типов)
        shop_id(int): required = True

    Returns:


    """
    def _create_demands_dict(query_set):
        tmp_dict = {}
        for x in query_set:
            dt = x.dttm_forecast.date()
            if dt not in tmp_dict:
                tmp_dict[dt] = {}
            tm = x.dttm_forecast.time()
            if tm not in tmp_dict[dt]:
                tmp_dict[dt][tm] = []
            tmp_dict[dt][tm].append(x)

        return tmp_dict

    operation_type_ids = form['operation_type_ids']

    shop = request.shop
    period_clients = PeriodClients.objects.select_related('operation_type__work_type').filter(
        operation_type__work_type__shop_id=shop.id
    )
    period_products = PeriodProducts.objects.select_related('operation_type__work_type').filter(
        operation_type__work_type__shop_id=shop.id
    )
    period_queues = PeriodQueues.objects.select_related('operation_type__work_type').filter(
        operation_type__work_type__shop_id=shop.id
    )
    
    if len(operation_type_ids) > 0:
        period_clients = [x for x in period_clients if x.operation_type_id in operation_type_ids]
        period_products = [x for x in period_products if x.operation_type_id in operation_type_ids]
        period_queues = [x for x in period_queues if x.operation_type_id in operation_type_ids]
    period_clients = _create_demands_dict(period_clients)
    period_products = _create_demands_dict(period_products)
    period_queues = _create_demands_dict(period_queues)
    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'], time()) + timedelta(days=1)
    dttm_step = timedelta(seconds=shop.system_step_in_minutes() * 60)
    forecast_periods = {x[0]: [] for x in PeriodClients.FORECAST_TYPES}
    for forecast_type, forecast_data in forecast_periods.items():
        for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
            clients = 0
            products = 0
            queue_wait_length = 0

            for x in period_clients.get(dttm.date(), {}).get(dttm.time(), []):
                if x.type != forecast_type:
                    continue
                clients += x.value
            for x in period_products.get(dttm.date(), {}).get(dttm.time(), []):
                if x.type != forecast_type:
                    continue
                products += x.value
            for x in period_queues.get(dttm.date(), {}).get(dttm.time(), []):
                if x.type != forecast_type:
                    continue
                queue_wait_length += x.value

            forecast_data.append({
                'dttm': BaseConverter.convert_datetime(dttm),
                'clients': clients,
                'products': products,
                'queue': queue_wait_length
            })

    return JsonResponse.success({k: v for k, v in forecast_periods.items()})


@api_method(
    'POST',
    SetDemandForm,
)
def set_demand(request, form):
    """
    Изменяет объекты PeriodDemand'ов с LONG_FORECAST умножая на multiply_coef, либо задавая значение set_value

    Args:
        method: POST
        url: /api/demand/set_demand
        from_dttm(QOS_DATETIME): required = True
        to_dttm(QOS_DATETIME): required = True
        operation_type_id(list): список типов касс (либо [] -- если для всех)
        multiply_coef(float): required = False
        set_value(float): required = False
        shop_id(int): required = True

    """
    models = []
    def save_models(lst, model):
        commit = False
        if model:
            lst.append(model)
            if len(lst) > 1000:
                commit = True
        else:
            commit = True

        if commit:
            PeriodClients.objects.bulk_create(lst)
            lst[:] = []

    operation_type_ids = form.get('operation_type_id', [])
    dttm_from = form['from_dttm']
    dttm_to = form['to_dttm']
    multiply_coef = form.get('multiply_coef')
    set_value = form.get('set_value')
    shop_id = request.shop.id
    if not len(operation_type_ids):
        operation_type_ids = OperationType.objects.select_related(
            'work_type'
        ).filter(
            dttm_added__gte=dttm_from,
            dttm_added__lte=dttm_to,
            work_type__shop_id=shop_id
        ).values_list('id', flat=True)
        
    period_clients = PeriodClients.objects.select_related(
        'operation_type__work_type'
    ).filter(
        operation_type__work_type__shop_id=shop_id,
        type=PeriodClients.LONG_FORECASE_TYPE,
        dttm_forecast__time__gte=dttm_from.time(),
        dttm_forecast__time__lte=dttm_to.time(),
        dttm_forecast__date__gte=dttm_from.date(),
        dttm_forecast__date__lte=dttm_to.date(),
        operation_type_id__in=operation_type_ids
    )

    if (set_value is not None):
        dttm_step = timedelta(seconds=request.shop.system_step_in_minutes() * 60)
        dates_needed = set()
        '''
        Создаем множество с нужными датами
        '''
        time_from = dttm_from.time()
        time_to = dttm_to.time()
        for date in range_u(dttm_from, dttm_to, timedelta(days=1)): #работает только с range_u
            date_from = datetime.combine(date, time_from)
            date_to = datetime.combine(date, time_to)
            dates_needed = dates_needed | {date for date in range_u(date_from, date_to, dttm_step)}
            #for time in range(date_from, date_to, dttm_step):
            #    dates_needed.add(time)
        '''
        Проходимся по всем операциям, для каждой операции получаем множетсво дат, которые уже
        указаны. Затем вычитаем из множества с нужными датами множество дат, которые уже есть.
        Потом итерируемся по резальтирующему множеству и для каждого элемента создаем PeriodClient
        с нужной датой, операцией и значением.
        '''
        for o_id in operation_type_ids:
            dates_to_add = set(period_clients.filter(operation_type_id=o_id).values_list('dttm_forecast', flat=True))
            dates_to_add = dates_needed.difference(dates_to_add)
            for date in dates_to_add:
                save_models(
                    models,
                    PeriodClients(
                        dttm_forecast = date, 
                        operation_type_id = o_id, 
                        value = set_value
                    )
                )
                #PeriodClients.objects.create(dttm_forecast = date, operation_type_id = o_id, value = set_value)
    save_models(models, None)
    changed_operation_type_ids = []
    for x in period_clients:
        if multiply_coef is not None:
            x.value *= multiply_coef
        else:
            x.value = set_value

        x.save()

        if x.operation_type_id not in changed_operation_type_ids:
            changed_operation_type_ids.append(x.operation_type_id)
    
    for x in changed_operation_type_ids:
        PeriodDemandChangeLog.objects.create(
            dttm_from=dttm_from,
            dttm_to=dttm_to,
            operation_type_id=x,
            multiply_coef=multiply_coef,
            set_value=set_value
        )
    return JsonResponse.success()


@api_method(
    'GET',
    GetDemandChangeLogsForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def get_demand_change_logs(request, form):
    """
    Вовращает список изменений по PeriodClients за текущий месяц

    Args:
         method: GET
         url: /api/demand/get_demand_change_logs
         work_type_ids(list): required = True
         from_dt(QOS_DATE): required = True
         to_dt(QOS_DATE): required = True
         shop_id(int): required = True
    """
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    if not form['work_type_id']:
        work_type_ids = WorkType.objects.filter(shop_id=form['shop_id'])
    else:
        work_type_ids = [form['work_type_id']]

    change_logs = PeriodDemandChangeLog.objects.filter(
        operation_type__work_type_id__in=work_type_ids,
        dttm_from__date__gte=from_dt,
        dttm_to__date__lte=to_dt,
    ).order_by('dttm_added')
    return JsonResponse.success([
        {
            'dttm_added': BaseConverter.convert_datetime(x.dttm_added),
            'dttm_from': BaseConverter.convert_datetime(x.dttm_from),
            'dttm_to': BaseConverter.convert_datetime(x.dttm_to),
            'work_type_id': x.operation_type.work_type_id,
            'multiply_coef': x.multiply_coef,
            'set_value': x.set_value,
        } for x in change_logs
    ])


@api_method('GET', GetVisitorsInfoForm)
def get_visitors_info(request, form):
    """
    Отдает информацию с камер по количеству посетителей

    Args:
        method: GET
        url: /api/demand/get_visitors_info
        from_dt(QOS_DATE): с какой даты смотрим
        to_dt(QOS_DATE):
        shop_id(int): чисто для api_method'a
    Returns:
        {
            'IncomeVisitors': [], |
            'PurchasesOutcomeVisitors': [], |
            'EmptyOutcomeVisitors': []
        }
    """
    def filter_qs(query_set, dttm):
        value_dttm_tuple = list(filter(lambda item_in_qs: item_in_qs[0] == dttm, query_set))
        return value_dttm_tuple[0][1] if value_dttm_tuple else 0

    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'] + timedelta(days=1), time())

    filter_dict = {
        'type': PeriodClients.FACT_TYPE,
        'dttm_forecast__gte': dttm_from,
        'dttm_forecast__lte': dttm_to,
    }

    return_dict = {
        'IncomeVisitors': [],
        'PurchasesOutcomeVisitors': [],
        'EmptyOutcomeVisitors': []
    }
    query_sets = {}

    for model_name in return_dict.keys():
        query_sets[model_name] = apps.get_model('db', model_name).objects.filter(**filter_dict).values_list(
            'dttm_forecast', 'value'
        )
    dttm = dttm_from
    while dttm < dttm_to:
        for model_name, qs in query_sets.items():
            return_dict[model_name].append({
                'dttm': BaseConverter.convert_datetime(dttm),
                'value': filter_qs(qs, dttm)
            })
        dttm += timedelta(minutes=30)

    return JsonResponse.success(return_dict)


@api_method('POST', CreatePredictBillsRequestForm)
def create_predbills_request(request, form):
    """
    Создает request на qos_algo на создание PeriodDemand'ов с dt

    Args:
        method: POST
        url: /api/demand/create_predbills
        shop_id(int): required = True
        dt(QOS_DATE): required = True . с какой даты создавать

    Note:
         На алгоритмах выставлено dt_start = dt, dt_end = dt_start + 1 месяц (с какого по какое создавать)

    Raises:
        JsonResponse.internal_error: если произошла ошибка при создании request'a
    """
    dt = form['dt']

    result = create_predbills_request_function(request.shop.id, dt)

    return JsonResponse.success() if result is True else result


@api_method('POST', SetPredictBillsForm)
def set_pred_bills(request, form):
    """
    ждет request'a от qos_algo. когда получает, записывает данные из data в базу данных

    Args:
        method: POST
        url: /api/demand/set_predbills
        data(dict):  data от qos_algo
        key(str): ключ
    """

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
            PeriodClients.objects.bulk_create(lst)
            lst[:] = []

    try:
        data = json.loads(form['data'])
    except:
        return JsonResponse.internal_error('cannot parse json')

    shop = Shop.objects.get(id=data['shop_id'])
    dt_from = BaseConverter.parse_date(data['dt_from'])
    dt_to = BaseConverter.parse_date(data['dt_to'])
    
    PeriodClients.objects.select_related('operation_type__work_type').filter(
        type=PeriodClients.LONG_FORECASE_TYPE,
        dttm_forecast__date__gte=dt_from,
        dttm_forecast__date__lte=dt_to,
        operation_type__work_type__shop_id=shop.id,
        operation_type__do_forecast__in=[OperationType.FORECAST_HARD, OperationType.FORECAST_LITE],
    ).delete()
    
    for period_demand_value in data['demand']:
        clients = period_demand_value['value']
        clients = 0 if clients < 0 else clients
        save_models(
            models_list,
            PeriodClients(
                type=PeriodClients.LONG_FORECASE_TYPE,
                dttm_forecast=BaseConverter.parse_datetime(period_demand_value['dttm']),
                operation_type_id=period_demand_value['work_type'],
                value=clients,
            )
        )

    # блок для составления спроса на слотовые типы касс (никак не зависит от data с qos_algo) -- всегда 1
    work_time_seconds = (shop.tm_shop_closes.hour - shop.tm_shop_opens.hour) * 3600 +\
                        (shop.tm_shop_closes.minute - shop.tm_shop_opens.minute) * 60
    if work_time_seconds <= 0:
        work_time_seconds += 3600 * 24

    time_step = shop.forecast_step_minutes.hour * 3600 + shop.forecast_step_minutes.minute * 60

    for operation in OperationType.objects.filter(work_type__shop_id=shop.id, do_forecast=OperationType.FORECAST_LITE):
        for dt_offset in range((dt_to - dt_from).days + 1):
            dttm_start = datetime.combine(dt_from + timedelta(days=dt_offset), shop.tm_shop_opens)
            for tm_offset in range(0, work_time_seconds, time_step):
                save_models(
                    models_list,
                    PeriodClients(
                        type=PeriodClients.LONG_FORECASE_TYPE,
                        dttm_forecast=dttm_start + timedelta(seconds=tm_offset),
                        operation_type=operation,
                        value=1,
                    )
                )

    save_models(models_list, None)

    employments = Employment.objects.filter(
        function_group__allowed_functions__func='set_demand',
        function_group__allowed_functions__access_type__in=[FunctionGroup.TYPE_SHOP, FunctionGroup.TYPE_SUPERSHOP],
        shop=shop,
    ).values_list('user_id', flat=True)

    notify4users = User.objects.filter(
        id__in=employments
    )

    Event.objects.mm_event_create(
        notify4users,
        text='Cоставлен новый спрос на период с {} по {}'.format(data['dt_from'], data['dt_to']),
        department=shop,
    )
    # уведомляшки всем
    # for u in User.objects.filter(
    #         shop=shop,
    #         function_group__allowed_functions__access_type__in=FunctionGroup.__INSIDE_SHOP_TYPES__
    # ):
    #     Notifications.objects.create(
    #         type=Notifications.TYPE_SUCCESS,
    #         to_worker=u,
    #         text='Был составлен новый спрос на период с {} по {}'.format(data['dt_from'], data['dt_to'])
    #     )

    return JsonResponse.success()
