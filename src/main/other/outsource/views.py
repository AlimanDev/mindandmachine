from src.db.models import (
    User,
    Shop,
    WorkerDay,
    WorkerDayCashboxDetails,
)
from .forms import (
    GetOutsourceWorkersForm,
    AddOutsourceWorkersForm,
)

from src.util.utils import api_method, JsonResponse
from src.util.models_converter import UserConverter, BaseConverter, WorkerDayConverter
from datetime import datetime, timedelta
from django.core.exceptions import ObjectDoesNotExist


@api_method('GET', GetOutsourceWorkersForm)
def get_outsource_workers(request, form):
    """
    Получить список аутсорс работников с from_dt до to_dt

    Args:
        method: 'GET'
        url: /api/other/outsource/get_outsource_workers
        shop_id(int): required = True
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True

    Returns:
        {
            | 'amount': количество аутсорсеров
            | 'outsource_workers': [список аутсорсеров]
        }

    Raises:
        JsonResponse.does_not_exists_error: если такого магазина нету
    """
    response_dict = {
        'max_amount': 0,
        'dates': {}
    }

    shop = request.shop

    from_dt = form['from_dt']
    to_dt = form['to_dt']
    date_response_dict = response_dict['dates']


    for date in range((to_dt - from_dt).days + 1):
        converted_date = BaseConverter.convert_date(from_dt + timedelta(days=date))
        date_response_dict[converted_date] = {
            'outsource_workers': [],
            'amount': 0
        }

    status_list = list(WorkerDayCashboxDetails.WORK_TYPES_LIST)
    status_list.append(WorkerDayCashboxDetails.TYPE_VACANCY)

    outsource_workerdays = WorkerDayCashboxDetails.objects.select_related(
        'worker_day',
        'worker_day__worker',
        'worker_day__shop',
        'work_type',
    ).filter(
        dttm_deleted__isnull=True,
        dttm_from__gte=from_dt,
        dttm_from__lt=to_dt + timedelta(days=1),
        work_type_id__in=[w.id for w in shop.worktype_set.all()],
        is_vacancy=True,
        status__in=status_list,
        worker_day__child__id__isnull=True
    )

    for wd in outsource_workerdays:
        converted_date = BaseConverter.convert_date(wd.dttm_from.date())

        # first_name = '№{}'.format(str(outsourcer_number + 1))
        try:
            data = {
                'dttm_work_start': BaseConverter.convert_time(wd.dttm_from.time()),
                'dttm_work_end': BaseConverter.convert_time(wd.dttm_to.time()),
                'work_type': wd.work_type_id,  #if wd.type == WorkerDay.Type.TYPE_WORKDAY.value else None
                'work_type_name': wd.work_type.name,  #if wd.type == WorkerDay.Type.TYPE_WORKDAY.value else None
                'id': wd.id,
            }
            if wd.worker_day:
                data['type'] = WorkerDayConverter.convert_type(wd.worker_day.type)
                data['first_name'] = wd.worker_day.worker.first_name
                data['last_name'] = wd.worker_day.worker.last_name
                data['shop'] = wd.worker_day.shop.title

            date_response_dict[converted_date]['outsource_workers'].append(data)
            date_response_dict[converted_date]['amount'] += 1

        except ObjectDoesNotExist:
            return JsonResponse.does_not_exists_error(
                'Ошибка в get_outsource_workers. Такого дня нет в расписании.'
            )

    max_outsource_worker_on_period = 0  # для рендера на фронте
    for v in date_response_dict.values():
        if v['amount'] > max_outsource_worker_on_period:
            max_outsource_worker_on_period = v['amount']

    response_dict['max_amount'] = max_outsource_worker_on_period

    return JsonResponse.success(response_dict)
