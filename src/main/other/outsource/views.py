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
from django.db import IntegrityError


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
    try:
        shop = Shop.objects.get(id=form['shop_id'])
    except Shop.DoesNotExist:
        return JsonResponse.does_not_exists_error('Такого магазина не существует.')

    from_dt = form['from_dt']
    to_dt = form['to_dt']
    max_outsource_worker_on_period = 0  # для рендера на фронте
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
            'work_type',
            'work_type__shop'
        ).filter(
            dttm_from__gte=from_dt + timedelta(days=date),
            dttm_to__lt=from_dt + timedelta(days=date+1),
            work_type_id__in=[w.id for w in shop.worktype_set.all()],
            is_vacancy=True,
            status__in=status_list
        )
        # outsource_workerdays = WorkerDay.objects.qos_current_version(
        #     ).select_related('worker').filter(
        #     worker__shop=shop,
        #     worker__attachment_group=User.GROUP_OUTSOURCE,
        #     worker__dt_hired__gte=from_dt + timedelta(days=date),
        #     worker__dt_fired__lte=from_dt + timedelta(days=date),
        # )
        outsource_workers_count_per_day = outsource_workerdays.count()
        if outsource_workers_count_per_day > 0:
            outsourcer_number = 0
            for wd in outsource_workerdays:
                # first_name = '№{}'.format(str(outsourcer_number + 1))
                try:
                    data ={
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
                        data['shop'] = wd.work_type.shop.title

                    date_response_dict[converted_date]['outsource_workers'].append(data)

                except ObjectDoesNotExist:
                    return JsonResponse.does_not_exists_error(
                        'Ошибка в get_outsource_workers. Такого дня нет в расписании.'
                    )
                outsourcer_number += 1
        date_response_dict[converted_date]['amount'] = outsource_workers_count_per_day
        if outsource_workers_count_per_day > max_outsource_worker_on_period:
            max_outsource_worker_on_period = outsource_workers_count_per_day

    response_dict['max_amount'] = max_outsource_worker_on_period

    return JsonResponse.success(response_dict)


@api_method('POST', AddOutsourceWorkersForm)
def add_outsource_workers(request, form):
    """
    Добавляет аутсорсеров на dt

    Args:
         method: POST
         url: /api/other/outsource/add_outsource_workers
         shop_id(int): required = True
         dt(QOS_DATE): required = True
         from_tm(QOS_TIME): required = True
         to_tm(QOS_TIME): required = True
         work_type_id(int): required = True
         amount(int): количество аутсорсеров, которое будет в этот день

    Returns:
        [
            Список добавленых аутсорсеров + время начала/конца рабочего дня + дата
        ]
    """
    shop_id = form['shop_id']
    amount = form['amount']
    dt = form['dt']
    from_tm = form['from_tm']
    to_tm = form['to_tm']
    work_type_id = form['work_type_id']

    if not amount or amount < 1:
        return JsonResponse.value_error('Некоректное число работников: {}'.format(amount))

    last_outsourcer_in_day = WorkerDay.objects.select_related('worker').filter(
        worker__shop_id=shop_id,
        worker__attachment_group=User.GROUP_OUTSOURCE,
        dt=dt,
    ).last()
    last_outsourcer_in_db = User.objects.filter(attachment_group=User.GROUP_OUTSOURCE).order_by('date_joined').last()
    if last_outsourcer_in_day:
        last_outsourcer_in_day_number = last_outsourcer_in_day.worker.first_name[1:]
    else:
        last_outsourcer_in_day_number = '0'
    if last_outsourcer_in_db:
        last_outsourcer_in_db_number = last_outsourcer_in_db.id
    else:
        last_outsourcer_in_db_number = User.objects.all().order_by('date_joined').last().id
    added_outsourcers = []

    for i in range(form['amount']):
        outsourcer_number = str(int(last_outsourcer_in_day_number) + i + 1)
        outsourcer_username = str(last_outsourcer_in_db_number + i + 1)
        # try:
        added = User.objects.create(
            shop_id=shop_id,
            attachment_group=User.GROUP_OUTSOURCE,
            first_name='№' + outsourcer_number,
            last_name='Наемный сотрудник',
            dt_hired=dt,
            dt_fired=dt,
            username='outsourcer_' + outsourcer_username,
            auto_timetable=False,
            salary=0
        )
        dttm_work_start = datetime.combine(dt, from_tm)
        dttm_work_end = datetime.combine(dt, to_tm)
        # except IntegrityError:
        #     return JsonResponse.internal_error('Не удалось добавить аутсорс сотрудника.')

        outsourcer_worker_day = WorkerDay.objects.create(
            worker=added,
            type=WorkerDay.Type.TYPE_WORKDAY.value,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=outsourcer_worker_day,
            work_type_id=work_type_id,
            dttm_from=dttm_work_start,
            dttm_to=dttm_work_end
        )
        added_outsourcers.append(UserConverter.convert(added))

    return JsonResponse.success(added_outsourcers)
