from datetime import datetime, timedelta, time, date

from src.db.models import (
    PeriodClients,
    PeriodProducts,
    PeriodQueues,
    CashboxType,
    PeriodDemandChangeLog,
    Shop,
    User,
)
from dateutil.relativedelta import relativedelta
from django.http.response import HttpResponse
from django.db.models import Sum
from src.util.collection import range_u
from src.util.models_converter import BaseConverter, PeriodDemandChangeLogConverter
from src.util.utils import api_method, JsonResponse, get_uploaded_file
from .forms import (
    GetForecastForm,
    SetDemandForm,
    GetIndicatorsForm,
    SetPredictBillsForm,
    CreatePredictBillsRequestForm,
    GetDemandChangeLogsForm,
    UploadDemandForm,
)
from .utils import create_predbills_request_function, set_pred_bills_function
from django.views.decorators.csrf import csrf_exempt
from src.util.forms import FormUtil
from django.core.exceptions import EmptyResultSet, ImproperlyConfigured


@api_method('GET', GetIndicatorsForm)
def get_indicators(request, form):
    """

    Args:
        method: GET
        url: /api/demand/get_indicators
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        type(str): тип forecast'a (L/S/F)
        shop_id(int): required = False
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            | 'mean_bills': int or None,
            | 'mean_codes': int or None,
            | 'mean_income': None,
            | 'mean_bill_codes': int or None,
            | 'mean_hour_bills': int or None,
            | 'mean_hour_codes': int or None,
            | 'mean_hour_income': None,
            | 'growth': int or None,
            | 'total_people': None,
            | 'total_bills': int,
            | 'total_codes': int,
            | 'total_income': None
        }

    """
    dt_from = form['from_dt']
    dt_to = form['to_dt']

    forecast_type = form['type']

    shop_id = FormUtil.get_shop_id(request, form)
    # checkpoint = FormUtil.get_checkpoint(form)

    period_filter_dict = {
        'cashbox_type__shop_id': shop_id,
        'type': forecast_type,
        'dttm_forecast__gte': datetime.combine(dt_from, time()),
        'dttm_forecast__lt': datetime.combine(dt_to, time()) + timedelta(days=1)
    }

    clients = PeriodClients.objects.select_related('cashbox_type').filter(**period_filter_dict).aggregate(Sum('value'))['value__sum']
    products = PeriodProducts.objects.select_related('cashbox_type').filter(**period_filter_dict).aggregate(Sum('value'))['value__sum']

    prev_clients = PeriodClients.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type=forecast_type,
        dttm_forecast__gte=datetime.combine(dt_from, time()) - timedelta(days=30),
        dttm_forecast__lt=datetime.combine(dt_to, time()) + timedelta(days=1) - timedelta(days=30)
    ).aggregate(Sum('value'))['value__sum']

    if prev_clients and prev_clients != 0:
        growth = (clients - prev_clients) / prev_clients * 100
    else:
        growth = None

    def __div_safe(__a, __b):
        return __a / __b if (__b > 0 and __b and __a) else None
    return JsonResponse.success({
        'total_bills': clients if clients else 0,  # может вернуть None
        'total_codes': products if products else 0,  # аналогично
        'total_income': None,
        'mean_bill_codes': __div_safe(products, clients),
        'growth': growth,
        'total_people': None,
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
        cashbox_type_ids(list): список типов касс (либо [] -- для всех типов)
        format(str): 'raw' или 'excel' , default='raw'
        shop_id(int): required = False

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

    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    cashbox_type_ids = form['cashbox_type_ids']

    shop_id = FormUtil.get_shop_id(request, form)

    period_clients = PeriodClients.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=shop_id
    )
    period_products = PeriodProducts.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=shop_id
    )
    period_queues = PeriodQueues.objects.select_related('cashbox_type').filter(
        cashbox_type__shop_id=shop_id
    )

    if len(cashbox_type_ids) > 0:
        period_clients = [x for x in period_clients if x.cashbox_type_id in cashbox_type_ids]
        period_products = [x for x in period_products if x.cashbox_type_id in cashbox_type_ids]
        period_queues = [x for x in period_queues if x.cashbox_type_id in cashbox_type_ids]

    period_clients = _create_demands_dict(period_clients)
    period_products = _create_demands_dict(period_products)
    period_queues = _create_demands_dict(period_queues)

    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'], time()) + timedelta(days=1)
    dttm_step = timedelta(minutes=30)

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

    period_demand_change_log = PeriodDemandChangeLog.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id
    )

    if len(cashbox_type_ids) > 0:
        period_demand_change_log = [x for x in period_demand_change_log if x.cashbox_type_id in cashbox_type_ids]

    period_demand_change_log = [x for x in period_demand_change_log if dttm_from < x.dttm_to or dttm_to > x.dttm_from]

    response = {
        'period_step': 30,
        'forecast_periods': {k: v for k, v in forecast_periods.items()},
        'demand_changes': [PeriodDemandChangeLogConverter.convert(x) for x in period_demand_change_log]
    }

    return JsonResponse.success(response)


@api_method(
    'POST',
    SetDemandForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def set_demand(request, form):
    """
    Изменяет объекты PeriodDemand'ов с LONG_FORECAST умножая на multiply_coef, либо задавая значение set_value

    Args:
        method: POST
        url: /api/demand/set_forecast
        from_dttm(QOS_DATETIME): required = True
        to_dttm(QOS_DATETIME): required = True
        cashbox_type_id(list): список типов касс (либо [] -- если для всех)
        multiply_coef(float): required = False
        set_value(float): required = False
        shop_id(int): required = True

    """
    cashbox_type_ids = form['cashbox_type_id']

    multiply_coef = form.get('multiply_coef')
    set_value = form.get('set_value')

    dttm_from = form['from_dttm']
    dttm_to = form['to_dttm']

    shop_id = FormUtil.get_shop_id(request, form)

    period_clients = PeriodClients.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type=PeriodClients.LONG_FORECASE_TYPE,
        dttm_forecast__gte=dttm_from,
        dttm_forecast__lte=dttm_to,
        cashbox_type_id__in=cashbox_type_ids
    )

    cashboxes_types = []
    for x in period_clients:
        if multiply_coef is not None:
            x.value *= multiply_coef
        else:
            x.value = set_value

        x.save()
        cashboxes_types.append(x.cashbox_type_id)
    cashboxes_types = list(set(cashboxes_types))

    for x in cashboxes_types:
        PeriodDemandChangeLog.objects.create(
            dttm_from=dttm_from,
            dttm_to=dttm_to,
            cashbox_type_id=x,
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
         cashbox_type_ids(list): required = True
    """
    dt_from = date.today().replace(day=1)
    dt_to = dt_from + relativedelta(months=1) - relativedelta(days=1)

    if form['cashbox_type_id'] == 0:
        cashbox_type_ids = CashboxType.objects.filter(shop_id=form['shop_id'])
    else:
        cashbox_type_ids = [form['cashbox_type_id']]

    change_logs = PeriodDemandChangeLog.objects.filter(
        cashbox_type_id__in=cashbox_type_ids,
        dttm_from__date__gte=dt_from,
        dttm_to__date__lte=dt_to,
    ).order_by('dttm_added')

    return JsonResponse.success({
        'total_count': change_logs.count(),
        'demand_change_logs': [{
            'dttm_added': BaseConverter.convert_datetime(x.dttm_added),
            'dttm_from': BaseConverter.convert_datetime(x.dttm_from),
            'dttm_to': BaseConverter.convert_datetime(x.dttm_to),
            'cashbox_type_id': x.cashbox_type_id,
            'multiply_coef': x.multiply_coef,
            'set_value': x.set_value,
        } for x in change_logs],
    })


@api_method(
    'POST',
    UploadDemandForm,
    groups=[User.GROUP_SUPERVISOR, User.GROUP_SUPERVISOR]
)
def upload_demand(request, form):
    """
    Принимает от клиента экселевский файл и загружает из него данные в бд

    Args:
         method: POST
         url: /api/demand/upload_demand
         shop_id(int): required = True
    """
    demand_file = get_uploaded_file(request)
    if isinstance(demand_file, HttpResponse):
        return demand_file

    from openpyxl import load_workbook
    try:
        worksheet = load_workbook(demand_file).active
    except KeyError:
        return JsonResponse.internal_error('Не удалось открыть активный лист.')

    list_to_create = []

    shop_id = form['shop_id']
    cash_column_num = 0
    time_column_num = 1
    value_column_num = 2
    datetime_format = '%d.%m.%Y %H:%M:%S'

    def create_demand_objs(obj=None):
        if obj is None:
            PeriodClients.objects.bulk_create(list_to_create)
        elif len(list_to_create) == 999:
            list_to_create.append(obj)
            PeriodClients.objects.bulk_create(list_to_create)
            list_to_create[:] = []
        else:
            list_to_create.append(obj)

    cashbox_types = list(CashboxType.objects.filter(shop_id=shop_id))

    ######################### сюда писать логику чтения из экселя ######################################################

    for index, row in enumerate(worksheet.rows):
        value = row[value_column_num].value
        if not isinstance(row[value_column_num].value, int):
            continue

        dttm = row[time_column_num].value
        if '.' not in dttm or ':' not in dttm:
            continue
        if not isinstance(dttm, datetime):
            try:
                dttm = datetime.strptime(dttm, datetime_format)
            except ValueError:
                return JsonResponse.value_error('Невозможно преобразовать время. Пожалуйста введите формат {}'.format(datetime_format))

        cashtype_name = row[cash_column_num].value
        cashtype_name = cashtype_name[:1].upper() + cashtype_name[1:].lower()  # учет регистра чтобы нормально в бд было

        ct_to_search = list(filter(lambda ct: ct.name == cashtype_name, cashbox_types))  # возвращает фильтр по типам
        if len(ct_to_search) == 1:
            PeriodClients.objects.filter(
                dttm_forecast=dttm,
                cashbox_type=ct_to_search[0],
                type=PeriodClients.FACT_TYPE
            ).delete()
            create_demand_objs(
                PeriodClients(
                    dttm_forecast=dttm,
                    cashbox_type=ct_to_search[0],
                    value=value,
                    type=PeriodClients.FACT_TYPE
                )
            )
        else:
            return JsonResponse.internal_error('Невозможно прочитать тип работ на строке №{}.'.format(index))

    ####################################################################################################################

    create_demand_objs(None)

    from_dt_to_create = PeriodClients.objects.filter(
        type=PeriodClients.FACT_TYPE,
        cashbox_type__shop_id=shop_id
    ).order_by('dttm_forecast').last().dttm_forecast.date() + relativedelta(days=1)

    return create_predbills_request_function(shop_id=shop_id, dt=from_dt_to_create)


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
    shop_id = FormUtil.get_shop_id(request, form)
    dt = form['dt']

    result = create_predbills_request_function(shop_id, dt)

    return JsonResponse.success() if result is True else result


@csrf_exempt
@api_method('POST', SetPredictBillsForm, auth_required=False, check_permissions=False)
def set_pred_bills(request, form):
    """
    ждет request'a от qos_algo. когда получает, записывает данные из data в базу данных

    Args:
        method: POST
        url: /api/demand/set_predbills
        data(str): json data от qos_algo
        key(str): ключ
    """
    set_pred_bills_function(form['data'], form['key'])

    return JsonResponse.success()
