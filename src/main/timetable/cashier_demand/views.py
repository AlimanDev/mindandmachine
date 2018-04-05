from src.db.models import WorkerDay, User, CashboxType, WorkerCashboxInfo
from src.main.timetable.cashier_demand.forms import GetWorkersForm
from src.main.timetable.cashier_demand.utils import filter_worker_day_by_dttm
from src.util.collection import group_by
from src.util.models_converter import CashboxTypeConverter, UserConverter, WorkerDayConverter, WorkerCashboxInfoConverter
from src.util.utils import api_method, JsonResponse


@api_method('GET')
def get_cashiers_timetable():
    pass


@api_method('GET', GetWorkersForm)
def get_workers(request, form):
    days = group_by(
        filter_worker_day_by_dttm(
            shop_id=request.user.shop_id,
            day_type=WorkerDay.Type.TYPE_WORKDAY.value,
            dttm_from=form['dttm_from'],
            dttm_to=form['dttm_to']
        ),
        group_key=lambda _: _.worker_id,
        sort_key=lambda _: _.dt
    )

    users_ids = list(days.keys())
    users = User.objects.filter(id__in=users_ids)
    cashbox_types = CashboxType.objects.filter(shop_id=request.user.shop_id)
    worker_cashbox_info = group_by(
        WorkerCashboxInfo.objects.filter(worker_id__in=users_ids),
        group_key=lambda _: _.worker_id
    )

    response = {
        'users': {
            u.id: {
                'u': UserConverter.convert(u),
                'd': [WorkerDayConverter.convert(x) for x in days.get(u.id, [])],
                'c': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])]
            }
            for u in users
        },
        'cashbox_types': {x.id: CashboxTypeConverter.convert(x) for x in cashbox_types}
    }

    return JsonResponse.success(response)
