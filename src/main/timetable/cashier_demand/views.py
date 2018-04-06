import random
from datetime import datetime, time, timedelta
from src.db.models import WorkerDay, User, CashboxType, WorkerCashboxInfo
from src.main.timetable.cashier_demand.forms import GetWorkersForm, GetCashiersTimetableForm
from src.main.timetable.cashier_demand.utils import filter_worker_day_by_dttm
from src.util.collection import group_by, range_u
from src.util.models_converter import CashboxTypeConverter, UserConverter, WorkerDayConverter, WorkerCashboxInfoConverter, BaseConverter
from src.util.utils import api_method, JsonResponse


@api_method('GET', GetCashiersTimetableForm)
def get_cashiers_timetable(request, form):
    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    shop = request.user.shop

    days = WorkerDay.objects.filter(
        worker_shop_id=shop.id,
        type=WorkerDay.Type.TYPE_WORKDAY.value,
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt'],
    )

    days_by_user = group_by(days, lambda _: _.worker_id)
    days_by_dt = group_by(days, lambda _: _.dt)

    users_ids = list(days_by_user.keys())
    users = {u.id: u for u in User.objects.filter(id__in=users_ids)}

    cashbox_types = CashboxType.objects.filter(shop_id=shop.id)
    worker_cashbox_info = group_by(
        WorkerCashboxInfo.objects.filter(worker_id__in=users_ids),
        group_key=lambda _: _.worker_id
    )

    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'], time())
    dttm_step = timedelta(minutes=30)

    real_cashiers = []
    predict_cashier_needs = []
    fact_cashier_needs = []
    for dttm in range_u(dttm_from, dttm_to, dttm_step):
        dttm_converted = BaseConverter.convert_datetime(dttm)

        real_cashiers.append({
            'dttm': dttm_converted,
            'amount': random.randint(5, 10)
        })
        predict_cashier_needs.append({
            'dttm': dttm_converted,
            'amount': random.randint(5, 10)
        })
        fact_cashier_needs.append({
            'dttm': dttm_converted,
            'amount': random.randint(5, 10)
        })

        # dt = dttm.date()
        # tm = dttm.time()
        #
        # real_cashiers_amount = 0
        # for u in days_by_dt.get(dt, []):
        #     if u.tm_work_start > tm or u.tm_work_end <= tm:
        #         continue
        #
        #     if datetime.combine(dt, u.tm_break_start) <= dttm < datetime.combine(dt, u.tm_break_start) + timedelta(hours=1):
        #         continue
        #
        #     real_cashiers_amount += 1
        #
        # real_cashiers.append({
        #     'dttm': dttm,
        #     'amount': real_cashiers_amount
        # })

    response = {
        'indicators': {
            'mean_notworking_persent': random.uniform(3, 7),
            'big_demand_persent': random.randint(0, 2),
            'cashier_amount': random.randint(50, 100),
            'FOT': -1,
            'need_cashier_amount': random.randint(50, 100),
            'change_amount': random.randint(10, 20)
        },
        'period_step': 30,
        'tt_periods': {
            'real_cashiers': real_cashiers,
            'predict_cashier_needs': predict_cashier_needs,
            'fact_cashier_needs': fact_cashier_needs
        }
    }

    return JsonResponse.success(response)


@api_method('GET', GetWorkersForm)
def get_workers(request, form):
    days = group_by(
        filter_worker_day_by_dttm(
            shop_id=request.user.shop_id,
            day_type=WorkerDay.Type.TYPE_WORKDAY.value,
            dttm_from=form['from_dttm'],
            dttm_to=form['to_dttm']
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
