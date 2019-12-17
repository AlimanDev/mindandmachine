from datetime import timedelta, datetime, time

from src.main.timetable.cashier_demand.utils import get_worker_timetable2 as get_worker_timetable

from src.db.models import (
    WaitTimeInfo,
    ProductionDay,
    WorkType,
    Shop,
    PeriodDemand,
    PeriodQueues,
)
from dateutil.relativedelta import relativedelta
from src.util.utils import api_method, outer_server
from .forms import (
    GetTimeDistributionForm,
    GetIndicatorsForm,
    ProcessForecastForm,
)
import json
import urllib
from src.util.utils import JsonResponse
from django.conf import settings

from src.util.models_converter import BaseConverter, ProductionDayConverter


@api_method('GET', GetIndicatorsForm)
def get_indicators(request, form):
    """
    Получить данные по очереди (по всем типа работ в магазе)

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

    """
    forecast_type = form['type']
    shop_id = form['shop_id']
    from_dttm = datetime.combine(form['from_dt'], time())
    to_dttm = datetime.combine(form['to_dt'], time())

    # try:
    #     linear_work_type = WorkType.objects.get(shop_id=shop_id, is_main_type=True)
    # except:
    #     return JsonResponse.internal_error('Cannot get linear cashbox')

    period_queues = PeriodQueues.objects.select_related('operation_type__work_type').filter(
        # work_type_id=linear_work_type.id,
        operation_type__work_type__shop_id=shop_id,
        type=forecast_type,
    )
    current_period_queues = period_queues.filter(dttm_forecast__gte=from_dttm, dttm_forecast__lte=to_dttm)
    prev_queues = period_queues.filter(
        dttm_forecast__gte=from_dttm - relativedelta(months=1),
        dttm_forecast__lte=to_dttm - relativedelta(months=1)
    )

    queue_wait_length = 0
    for x in current_period_queues:
        queue_wait_length += x.value

    prev_queue_wait_length = 0
    for x in prev_queues:
        prev_queue_wait_length += x.value

    mean_length = queue_wait_length / len(period_queues) if len(period_queues) > 0 else None
    mean_wait_time = None
    if prev_queue_wait_length:
        length_change = (queue_wait_length - prev_queue_wait_length) / prev_queue_wait_length * 100
    else:
        length_change = None

    return JsonResponse.success({
        'mean_length': mean_length,
        'mean_wait_time': mean_wait_time,
        'length_change': length_change,
    })


@api_method('GET', GetTimeDistributionForm)
def get_time_distribution(request, form):
    """
    Args:
        method: GET
        url: /api/queue/get_time_distribution
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        work_type_ids(list): required = True (либо [] -- для всех типов касс)
        shop_id(int): required = False

    Todo:
        Сделать описание. Непонятно что делает функция
    """
    work_type_ids = form['work_type_ids']

    shop_id = form['shop_id']

    wait_time_info = WaitTimeInfo.objects.select_related(
        'work_type'
    ).filter(
        work_type__shop_id=shop_id,
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt']
    )

    def __add(__dict, __key, __default):
        if __key not in __dict:
            __dict[__key] = __default
        return __dict[__key]

    tmp = {}
    for x in wait_time_info:
        el = __add(tmp, x.work_type_id, {})
        el = __add(el, x.type, {})
        el = __add(el, x.dt, [])
        el.append(x)
    wait_time_info = tmp

    work_types = WorkType.objects.filter(shop_id=shop_id)
    if len(work_type_ids) > 0:
        work_types = [x for x in work_types if x.id in work_type_ids]

    result = {}
    for work_type in work_types:
        result[work_type.id] = {}

        for forecast_type in PeriodDemand.FORECAST_TYPES:
            arr = []
            for i in range(1, 10):
                arr.append({
                    'wait_time': i,
                    'proportion': int(30 * (1 - (i-1)/10))
                })
            result[work_type.id][forecast_type[0]] = arr

    return JsonResponse.success(result)


@api_method(
    'POST',
    ProcessForecastForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def process_forecast(request, form):
    """
    на основания объема работ и составленного расписания отправляет запрос на составления расписания
    Args:
         method: POST
         url: /api/queue/process_forecast
         shop_id(int): required = True
    Returns:
        None
    """

    predict2days = 62

    shop = request.shop
    dt_now = datetime.now().date()
    work_type = WorkType.objects.filter(shop=shop).order_by('id').first()

    day_info = ProductionDay.objects.filter(
        dt__gte=dt_now - timedelta(days=366),
        dt__lte=dt_now + timedelta(days=predict2days),
        region_id=shop.region_id,
    )

    queue = PeriodQueues.objects.filter(
        operation_type__work_type__id=work_type.id,
        type=PeriodQueues.FACT_TYPE,
        dttm_forecast__date__gte=dt_now - timedelta(days=366),
        dttm_forecast__lte=dt_now + timedelta(days=1)
    ).order_by('dttm_forecast')

    if not queue:
        return JsonResponse.value_error('В базе данных нет данных по фактическому спросу для составления.')

    from_dt = queue[0].dttm_forecast.date()
    form_tt_prev = {
        'from_dt': from_dt,
        'to_dt': dt_now + timedelta(days=1),
        'work_type_ids': [work_type.id],
        'position_id': False,
    }

    form_tt_predict = {
        'from_dt': dt_now,
        'to_dt': dt_now + timedelta(days=predict2days),
        'work_type_ids': [work_type.id],
        'position_id': False,
    }


    data_prev = get_worker_timetable(shop.id, form_tt_prev)
    data_predict = get_worker_timetable(shop.id, form_tt_predict)

    if type(data_prev) == dict and type(data_predict) == dict:
        # train set
        prev_data = []
        it_needs = 0
        it_real = 0

        needs = data_prev['tt_periods']['predict_cashier_needs']
        real_tt = data_prev['tt_periods']['real_cashiers']
        for queue_period in queue:
            elem = {
                'value': queue_period.value,
                'dttm': BaseConverter.convert_datetime(queue_period.dttm_forecast),
                'work_type': queue_period.work_type_id,
            }
            while needs[it_needs]['dttm'] != elem['dttm']:  # needs and queue are ordered
                it_needs += 1

            while real_tt[it_real]['dttm'] != elem['dttm']:  # needs and queue are ordered
                it_real += 1

            elem['work_amount'] = needs[it_needs]['amount']
            elem['n_cashiers'] = real_tt[it_real]['amount']
            prev_data.append(elem)

        # predict
        prediction_data = []

        needs = data_predict['tt_periods']['predict_cashier_needs']
        real_tt = data_predict['tt_periods']['real_cashiers']
        for it_needs, real_period in enumerate(real_tt):
            prediction_data.append({
                'n_cashiers': real_period['amount'],
                'work_amount': needs[it_needs]['amount'],
                'dttm': real_period['dttm'],
                'work_type': work_type.id,
            })

        aggregation_dict = {
            'IP': settings.HOST_IP,
            'algo_params': {
                'days_info': [ProductionDayConverter.convert(day) for day in day_info],
                'dt_from': BaseConverter.convert_date(dt_now),
                'dt_to': BaseConverter.convert_date(dt_now + timedelta(days=predict2days)),
                # 'dt_start': BaseConverter.convert_date(dt),
                # 'days': predict2days,
                'period_step': BaseConverter.convert_time(shop.forecast_step_minutes),
                'tm_start': BaseConverter.convert_time(shop.dt_opened),
                'tm_end': BaseConverter.convert_time(shop.dt_closed),
            },
            'prediction_data': prediction_data,
            'prev_data': prev_data,
            'work_types': {
                work_type.id:  {
                    'id': work_type.id,
                    'predict_demand_params':  json.loads(work_type.period_queue_params),
                    'name': work_type.name

                }
            },
            'shop_id': shop.id,
        }

        data = json.dumps(aggregation_dict).encode('ascii')
        req = urllib.request.Request('http://{}/create_queue'.format(settings.TIMETABLE_IP), data=data,
                              headers={'content-type': 'application/json'})
        try:
            response = urllib.request.urlopen(req)
        except urllib.request.HTTPError:
            raise JsonResponse.algo_internal_error('Ошибка при чтении ответа от второго сервера.')
        except urllib.error.URLError:
            return JsonResponse.algo_internal_error('Сервер для обработки алгоритма недоступен.')
        task_id = json.loads(response.read().decode('utf-8')).get('task_id')
        if task_id is None:
            return JsonResponse.algo_internal_error('Ошибка при создании задачи на исполненение.')

    else:
        return JsonResponse.value_error('что-то пошло не по плану')
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
        work_type__shop_id=shop.id,
    ).delete()

    for period_demand_value in data['queue_len']:
        clients = period_demand_value['value']
        clients = 0 if clients < 0 else clients
        save_models(
            models_list,
            PeriodQueues(
                type=PeriodQueues.LONG_FORECASE_TYPE,
                dttm_forecast=BaseConverter.parse_datetime(period_demand_value['dttm']),
                operation_type__work_type_id=period_demand_value['work_type'],
                value=clients,
            )
        )

    save_models(models_list, None)

    # уведомляшки всем
    # for u in User.objects.filter(
    #         shop=shop,
    #         function_group__allowed_functions__access_type__in=FunctionGroup.__INSIDE_SHOP_TYPES__
    # ):
    #     Notifications.objects.create(
    #         type=Notifications.TYPE_SUCCESS,
    #         to_worker=u,
    #         text='Был составлен новый прогноз очереди на период с {} по {}'.format(data['dt_from'], data['dt_to'])
    #     )

    return JsonResponse.success()