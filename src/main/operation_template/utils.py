"""
Note:
    Во всех функциях, которые ищут сотрудников для замены в качестве аргумента используется

    arguments_dict = {
        | 'shop_id': int,
        | 'dttm_exchange_start(datetime.datetime): дата-время, на которые искать замену,
        | 'dttm_exchange_end(datetime.datetime): дата-время, на которые искать замену,
        | 'work_type'(int): на какую специализацию ищем замену,
        | 'predict_demand'(list): QuerySet PeriodDemand'ов,
        | 'mean_bills_per_step'(dict): по ключу -- id типа кассы, по значению -- средняя скорость,
        | 'work_types_dict'(dict): по ключу -- id типа кассы, по значению -- объект
        | 'users_who_can_work(list): список пользователей, которые могут работать на ct_type
    }

    Если одна из функций падает, рейзим ValueError, во вьюхе это отлавливается, и возвращается в 'info' в какой \
    именно функции произошла ошибка.

    А возвращается:
        {
            user_id: {
                | 'type': ,
                | 'tm_start': ,
                | 'tm_end':
            }, ..
        }
"""
from datetime import date, timedelta
from django.utils.timezone import now


from src.db.models import (
    OperationTemplate,
    PeriodClients
)


def build_period_clients(operation_template, dt_from=None, dt_to=None, operation='create'):
    dt_min = now().date() + timedelta(days = 2)

    if not dt_to:
        dt_to = dt_min + timedelta(days=62)

    if operation_template.dt_built_to:
        if (not dt_from \
            or dt_from > operation_template.dt_built_to):
            dt_from = operation_template.dt_built_to + timedelta(days=1)
        if dt_to < operation_template.dt_built_to:
            dt_to = operation_template.dt_built_to

    if not dt_from:
        dt_from = dt_min


    period_clients = PeriodClients.objects.filter(
        operation_type=operation_template.operation_type,
        dttm_forecast__gte=dt_from,
        dttm_forecast__lte=dt_to,
        ).order_by(
        'dttm_forecast')
    period_clients = period_clients.iterator()
    try:
        period = next(period_clients)
    except StopIteration:
        pass

    for date in operation_template.generate_dates(dt_from, dt_to):
        while period and period.dttm_forecast < date:
            period = next(period_clients, None)
        if period and period.dttm_forecast == date:
            if operation=='create':
                period.value += operation_template.value
            else:
                period.value -= operation_template.value
                if period.value < 0:
                    period.value = 0
            period.save()
            period = next(period_clients, None)
        elif operation=='create':
            PeriodClients.objects.create(
                dttm_forecast=date,
                value=operation_template.value,
                type=PeriodClients.LONG_FORECASE_TYPE,
                operation_type_id=operation_template.operation_type_id
                )
    operation_template.dt_built_to = dt_to
    operation_template.save()


