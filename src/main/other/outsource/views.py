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
from src.util.models_converter import UserConverter
from datetime import datetime


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
    response_dict = {}
    try:
        shop = Shop.objects.get(id=form['shop_id'])
    except Shop.DoesNotExist:
        return JsonResponse.does_not_exists_error('Такого магазина не существует.')

    from_dt = form['from_dt']
    to_dt = form['to_dt']

    outsource_workers = User.objects.filter(
        shop=shop,
        attachment_group=User.GROUP_OUTSOURCE,
        dt_hired__gte=from_dt,
        dt_fired__lte=to_dt
    )
    response_dict['outsource_workers'] = [UserConverter.convert(u) for u in outsource_workers]
    response_dict['amount'] = outsource_workers.count()

    return JsonResponse.success(response_dict)


@api_method('GET', AddOutsourceWorkersForm)
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
         cashbox_type_id(int): required = True
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
    cashbox_type_id = form['cashbox_type_id']

    if not amount or amount < 1:
        return JsonResponse.value_error('Некоректное число работников: {}'.format(amount))

    last_outsourcer = User.objects.filter(shop_id=shop_id, attachment_group=User.GROUP_OUTSOURCE).last()
    if last_outsourcer:
        last_outsourcer_number = last_outsourcer.last_name[1:]
    else:
        last_outsourcer_number = '0'
    added_outsourcers = []

    for i in range(form['amount']):
        outsourcer_number = str(int(last_outsourcer_number) + i + 1)
        added = User.objects.create(
            shop_id=shop_id,
            attachment_group=User.GROUP_OUTSOURCE,
            first_name='Наемный сотрудник',
            last_name='№' + outsourcer_number,
            dt_hired=dt,
            dt_fired=dt,
            username='outsourcer_' + outsourcer_number,
            auto_timetable=False
        )
        dttm_work_start = datetime.combine(dt, from_tm)
        dttm_work_end = datetime.combine(dt, to_tm)

        outsourcer_worker_day = WorkerDay.objects.create(
            worker=added,
            type=WorkerDay.Type.TYPE_WORKDAY.value,
            dt=dt,
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=outsourcer_worker_day,
            cashbox_type_id=cashbox_type_id,
            dttm_from=dttm_work_start,
            dttm_to=dttm_work_end
        )
        added_outsourcers.append(UserConverter.convert(added))

    return JsonResponse.success(added_outsourcers)
