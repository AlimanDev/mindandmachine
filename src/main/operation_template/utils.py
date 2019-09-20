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
from django.db.models.functions import Greatest
from django.db.models import F

from src.db.models import (
    OperationTemplate,
    PeriodClients
)


def build_period_clients(operation_template, dt_from=None, dt_to=None, operation='create'):
    """ При operation='create' создает потребность в PeriodClients
            в соответствии с шаблоном.
        При operation='delete' - удаляет
        По умолчанию на 62 дня вперед, начиная с послезавтра
    """
    dt_min = now().date() + timedelta(days=2)

    if not dt_to:
        dt_to = dt_min + timedelta(days=62)

    if operation_template.dt_built_to:
        if not dt_from or dt_from > operation_template.dt_built_to:
            dt_from = operation_template.dt_built_to + timedelta(days=1)
        if dt_to < operation_template.dt_built_to:
            dt_to = operation_template.dt_built_to

    if not dt_from:
        dt_from = dt_min

    # Добавить транзакцию
    period_clients = PeriodClients.objects.filter(
        operation_type=operation_template.operation_type,
        dttm_forecast__gte=dt_from,
        dttm_forecast__lte=dt_to+timedelta(days=1),
    ).order_by(
        'dttm_forecast'
    )
    period_clients = period_clients.iterator()
    period = None
    try:
        period = next(period_clients)
    except StopIteration:
        pass


    sign = 1 if operation=='create' else -1

    updates = []
    creates = []

    # Ищем нужные нам интервалы в period clients.
    # Найденным записям увеличиваем значение по шаблону.
    # Если не нашли - создаем новую запись
    for date in operation_template.generate_dates(dt_from, dt_to):
        while period and period.dttm_forecast < date:
            period = next(period_clients, None)
        if period and period.dttm_forecast == date:
            updates.append(period.id)
            period = next(period_clients, None)
        elif operation=='create':
            creates.append(
                PeriodClients(
                    dttm_forecast=date,
                    value=operation_template.value,
                    type=PeriodClients.LONG_FORECASE_TYPE,
                    operation_type_id=operation_template.operation_type_id
                    ))

    if len(creates):
        PeriodClients.objects.bulk_create(creates)
    if len(updates):
        PeriodClients.objects.filter(id__in=updates).update(
            value = Greatest(F('value') + operation_template.value * sign, 0)
            )

    operation_template.dt_built_to = dt_to
    operation_template.save()
