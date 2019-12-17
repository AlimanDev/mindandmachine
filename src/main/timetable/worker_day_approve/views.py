from django.utils.timezone import now

from dateutil.relativedelta import relativedelta
from datetime import date

from src.timetable.models import (
    WorkerDay,
    WorkerDayApprove,
)

from src.util.utils import JsonResponse, api_method
from src.util.models_converter import (
    WorkerDayApproveConverter,
)
from .forms import (
    GetWorkerDayApprovesForm,
    WorkerDayApproveForm,
    DeleteWorkerDayApproveForm,
)


@api_method(
    'GET',
    GetWorkerDayApprovesForm,
)
def get_worker_day_approves(request, form):
    """
    Подтверждения расписания

    Args:
        method: GET
        url: /api/worker_day_approve/get_worker_day_approves
        'shop_id': id магазина
        'dt_from' : дата с
        'dt_to' : дата по

    Returns:
        [{
            | 'id': id шаблона,
            | 'shop_id': название,
            | 'dt_approved': 1 число подтвежденного месяца,
            | 'dttm_added': когда добавлено,
            | 'created_by': кем создан,
        },
        ...
        ]
    """
    shop = request.shop
    worker_day_approve = WorkerDayApprove.objects.filter(
        shop_id = shop.id
    )
    if form['dt_approved']:
        worker_day_approve = worker_day_approve.filter(
        dt_approved=form['dt_approved'],
        )
    if form['dt_to']:
        worker_day_approve = worker_day_approve.filter(
        dttm_added__lte=form['dt_to'],
        )
    if form['dt_from']:
        worker_day_approve = worker_day_approve.filter(
        dttm_added__gte=form['dt_from'],
        )

    return JsonResponse.success([
        WorkerDayApproveConverter.convert(wda) for wda in worker_day_approve
    ])


@api_method(
    'POST',
    WorkerDayApproveForm,
)
def create_worker_day_approve(request, form):
    """
    Создает новое подтверждение расписания

    Args:
        method: POST
        url: /api/worker_day_approve/create_worker_day_approve
        'shop_id': id магазина
        'month' : подтверждаемый месяц
        'year' : год месяца

    Returns:
        {
            | 'id': id шаблона,
            | 'shop_id': название,
            | 'dt_approved': 1 число подтвежденного месяца,
            | 'dttm_added': когда добавлено,
            | 'created_by': кем создан,
        }
    """
    dt = date(form['year'], form['month'], 1)
    dt_end = dt + relativedelta(months=1)
    worker_day_approve = WorkerDayApprove.objects.create(
        shop_id = form['shop_id'],
        created_by = request.user,
        dt_approved=dt,
    )

    WorkerDay.objects.filter(
        employment__shop_id=form['shop_id'],
        dt__gte=dt,
        dt__lt=dt_end,
        worker_day_approve_id__isnull=True
    ).update(worker_day_approve=worker_day_approve)


    return JsonResponse.success(
        WorkerDayApproveConverter.convert(worker_day_approve)
    )


@api_method(
    'POST',
    DeleteWorkerDayApproveForm,
    lambda_func=lambda x: WorkerDayApprove.objects.get(id=x['id']).shop
)

def delete_worker_day_approve(request, form):
    """
    "Удаляет" шаблон операции с заданным номером

    Args:
        method: POST
        url: /api/worker_day_approve/delete_worker_day_approve
        id(int): required = True

    Returns:

    """

    try:
        worker_day_approve = WorkerDayApprove.objects.get(
            id=form['id'],
        )
    except WorkerDayApprove.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    worker_day_approve.dttm_deleted = now()
    worker_day_approve.save()

    WorkerDay.objects.filter(
        worker_day_approve_id=form['id']
    ).update(worker_day_approve=None)

    return JsonResponse.success()
