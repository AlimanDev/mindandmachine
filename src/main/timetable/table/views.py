from src.db.models import User, WorkerCashboxInfo, WorkerDay
from src.util.models_converter import UserConverter
from src.util.utils import api_method, JsonResponse
from .forms import SelectCashiersForm


@api_method('GET', SelectCashiersForm)
def select_cashiers(request, form):
    shop_id = request.user.shop_id

    users = User.objects.filter(shop_id=shop_id)

    cashboxes_type_ids = set(form.get('cashbox_types', []))
    if len(cashboxes_type_ids) > 0:
        users_hits = set()
        for x in WorkerCashboxInfo.objects.select_related('cashbox_type').filter(cashbox_type__shop_id=shop_id, is_active=True):
            if x.cashbox_type_id in cashboxes_type_ids:
                users_hits.add(x.worker_id)

        users = [x for x in users if x.id in users_hits]

    cashier_ids = set(form.get('cashier_ids', []))
    if len(cashier_ids) > 0:
        users = [x for x in users if x.id in cashier_ids]

    work_types = set(form.get('work_types', []))
    if len(work_types) > 0:
        users = [x for x in users if x.work_type in work_types]

    worker_days = WorkerDay.objects.filter(worker_shop_id=shop_id)

    workday_type = form.get('workday_type')
    if workday_type is not None:
        worker_days = worker_days.filter(type=workday_type)

    workdays = form.get('workdays')
    if len(workdays) > 0:
        worker_days = worker_days.filter(dt__in=workdays)

    common_users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]

    work_workdays = form.get('work_workdays', [])
    if len(work_workdays) > 0:
        worker_days = WorkerDay.objects.filter(worker_shop_id=shop_id, type=WorkerDay.Type.TYPE_WORKDAY.value, dt__in=work_workdays)

        tm_from = form.get('from_tm')
        if tm_from is not None:
            worker_days = worker_days.filter(tm_work_end__gt=tm_from)

        tm_to = form.get('tm_to')
        if tm_to is not None:
            worker_days = worker_days.filter(tm_work_start__lt=tm_to)

        work_users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]
    else:
        work_users = []

    return JsonResponse.success({
        'common': {x.id: UserConverter.convert(x) for x in common_users},
        'work': {x.id: UserConverter.convert(x) for x in work_users}
    })
