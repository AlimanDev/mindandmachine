from datetime import datetime, time, timedelta

from django.shortcuts import redirect

from src.db.models import WorkerDay, User, CashboxType, WorkerCashboxInfo, WorkerDayCashboxDetails, PeriodDemand
from src.main.timetable.cashier_demand.forms import GetWorkersForm, GetCashiersTimetableForm
from src.util.collection import range_u
from src.util.models_converter import CashboxTypeConverter, UserConverter, WorkerDayConverter, WorkerCashboxInfoConverter, BaseConverter
from src.util.utils import api_method, JsonResponse


@api_method('GET', GetCashiersTimetableForm)
def get_cashiers_timetable(request, form):
    shop = request.user.shop

    if form['format'] == 'excel':
        if shop.hidden_title == 'shop004':
            return redirect('/api/_i/media/timetable_temp/shop004.xlsx')

        return JsonResponse.value_error('Excel is not supported yet')

    worker_day_cashbox_detail = WorkerDayCashboxDetails.objects.select_related(
        'worker_day', 'on_cashbox'
    ).filter(
        worker_day__worker_shop_id=shop.id,
        worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
        worker_day__dt__gte=form['from_dt'],
        worker_day__dt__lte=form['to_dt'],
    )

    cashbox_type_ids = form['cashbox_type_ids']
    if len(cashbox_type_ids) > 0:
        worker_day_cashbox_detail = [x for x in worker_day_cashbox_detail if x.on_cashbox.type_id in cashbox_type_ids]

    period_demand = list(
        PeriodDemand.objects.select_related(
            'cashbox_type'
        ).filter(
            cashbox_type__shop_id=shop.id
        )
    )
    if len(cashbox_type_ids) > 0:
        period_demand = [x for x in period_demand if x.cashbox_type_id in cashbox_type_ids]

    tmp = {}
    for x in period_demand:
        dt = x.dttm_forecast.date()
        if dt not in tmp:
            tmp[dt] = {}

        tm = x.dttm_forecast.time()
        if tm not in tmp[dt]:
            tmp[dt][tm] = []

        tmp[dt][tm].append(x)
    period_demand = tmp

    users = {}
    for x in worker_day_cashbox_detail:
        worker_id = x.worker_day.worker_id
        if worker_id not in users:
            users[worker_id] = {
                'days': {},
                'cashbox_info': {}
            }
        user_item = users[worker_id]

        dt = x.worker_day.dt
        if dt not in user_item['days']:
            user_item['days'][dt] = {
                'day': x.worker_day,
                'details': []
            }

        user_item['days'][dt]['details'].append(x)

    users_ids = list(users.keys())
    worker_cashbox_info = WorkerCashboxInfo.objects.filter(is_active=True, worker_id__in=users_ids)
    for x in worker_cashbox_info:
        users[x.worker_id]['cashbox_info'][x.cashbox_type_id] = x

    dttm_from = datetime.combine(form['from_dt'], time())
    dttm_to = datetime.combine(form['to_dt'], time()) + timedelta(days=1)
    dttm_step = timedelta(minutes=30)

    real_cashiers_total_amount = 0
    mean_notworking_present = 0
    cashier_amount_max = 0
    big_demand_persent = 0
    need_cashier_amount_max = 0

    today = datetime.now().date()

    users_amount_set = set()

    real_cashiers = []
    predict_cashier_needs = []
    fact_cashier_needs = []
    for dttm in range_u(dttm_from, dttm_to, dttm_step, False):
        dttm_converted = BaseConverter.convert_datetime(dttm)

        dt = dttm.date()
        tm = dttm.time()

        predict_cheques_long = 0
        predict_cheques_fact = 0
        for x in period_demand.get(dt, {}).get(tm, []):
            if x.type == PeriodDemand.Type.LONG_FORECAST.value:
                predict_cheques_long += x.clients
            elif x.type == PeriodDemand.Type.FACT.value:
                predict_cheques_fact += x.clients

        real_cashiers_amount = 0
        cheques_amount = 0
        for uid, user in users.items():
            if dt not in user['days']:
                continue

            day = user['days'][dt]['day']
            details = user['days'][dt]['details']

            cashbox = []
            for d in details:
                if d.tm_from < d.tm_to:
                    if d.tm_from <= tm < d.tm_to:
                        cashbox.append(d)
                else:
                    if d.tm_from <= tm or d.tm_to > tm:
                        cashbox.append(d)

            if len(cashbox) == 0:
                continue

            if day.tm_break_start is not None:
                if datetime.combine(dt, day.tm_break_start) <= dttm < datetime.combine(dt, day.tm_break_start) + timedelta(hours=1):
                    continue

            cashbox_type = cashbox[0].on_cashbox.type_id
            cashbox_info = user['cashbox_info'].get(cashbox_type)
            mean_speed = cashbox_info.mean_speed if cashbox_info is not None else 0

            real_cashiers_amount += 1
            users_amount_set.add(uid)
            cheques_amount += mean_speed * shop.beta

        real_cashiers_total_amount += real_cashiers_amount
        cashier_amount_max = max(real_cashiers_amount, cashier_amount_max)

        if predict_cheques_fact < cheques_amount:
            mean_notworking_present += (1 - predict_cheques_fact / cheques_amount) * real_cashiers_amount

        if dt < today:
            if predict_cheques_fact > cheques_amount * 2:
                big_demand_persent += 1
        else:
            if predict_cheques_long > cheques_amount * 2:
                big_demand_persent += 1

        predict_cashier_needs_amount = predict_cheques_long / 15

        if dt >= today:
            need_cashier_amount_max = max(predict_cashier_needs_amount - real_cashiers_amount, need_cashier_amount_max)

        real_cashiers.append({
            'dttm': dttm_converted,
            'amount': real_cashiers_amount
        })

        predict_cashier_needs.append({
            'dttm': dttm_converted,
            'amount': predict_cashier_needs_amount
        })

        fact_cashier_needs.append({
            'dttm': dttm_converted,
            'amount': predict_cheques_fact / 15
        })

    mean_notworking_present = mean_notworking_present / real_cashiers_total_amount if real_cashiers_total_amount > 0 else 0

    response = {
        'indicators': {
            'mean_notworking_persent': -1,  # mean_notworking_present,
            'big_demand_persent': big_demand_persent,
            'cashier_amount': len(users_amount_set),
            'FOT': -1,
            'need_cashier_amount': 0,  # need_cashier_amount_max,
            'change_amount': 10
        },
        'period_step': 30,
        'tt_periods': {
            # очень грязный хак, потому что графики перепутаны
            # 'real_cashiers': fact_cashier_needs,
            # 'predict_cashier_needs': predict_cashier_needs,
            # 'fact_cashier_needs': real_cashiers
            'real_cashiers': real_cashiers,
            'predict_cashier_needs': predict_cashier_needs,
            'fact_cashier_needs': fact_cashier_needs
        }
    }

    return JsonResponse.success(response)


# @api_method('GET', GetWorkersForm)
# def get_workers(request, form):
#     shop = request.user.shop
#
#     days = {
#         d.id: d for d in filter_worker_day_by_dttm(
#             shop_id=request.user.shop_id,
#             day_type=WorkerDay.Type.TYPE_WORKDAY.value,
#             dttm_from=form['from_dttm'],
#             dttm_to=form['to_dttm']
#         )
#     }
#
#     worker_day_cashbox_detail = WorkerDayCashboxDetails.objects.select_related(
#         'worker_day', 'on_cashbox'
#     ).filter(
#         worker_day__worker_shop_id=shop,
#         worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
#         worker_day__dt__gte=form['from_dttm'].date(),
#         worker_day__dt__lte=form['to_dttm'].date(),
#     )
#
#     cashbox_type_ids = form['cashbox_type_ids']
#     if len(cashbox_type_ids) > 0:
#         worker_day_cashbox_detail = [x for x in worker_day_cashbox_detail if x.on_cashbox.type_id in cashbox_type_ids]
#
#     tmp = []
#     for d in worker_day_cashbox_detail:
#         x = days.get(d.worker_day_id)
#         if x is not None:
#             tmp.append(x)
#     days = group_by(tmp, group_key=lambda _: _.worker_id, sort_key=lambda _: _.dt)
#
#     users_ids = list(days.keys())
#     users = User.objects.filter(id__in=users_ids)
#     cashbox_types = CashboxType.objects.filter(shop_id=shop.id)
#
#     worker_cashbox_info = group_by(
#         WorkerCashboxInfo.objects.filter(worker_id__in=users_ids),
#         group_key=lambda _: _.worker_id
#     )
#
#     response = {
#         'users': {
#             u.id: {
#                 'u': UserConverter.convert(u),
#                 'd': [WorkerDayConverter.convert(x) for x in days.get(u.id, [])],
#                 'c': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])]
#             }
#             for u in users
#         },
#         'cashbox_types': {x.id: CashboxTypeConverter.convert(x) for x in cashbox_types}
#     }
#
#     return JsonResponse.success(response)

@api_method('GET', GetWorkersForm)
def get_workers(request, form):
    shop = request.user.shop

    from_dt = form['from_dttm'].date()
    from_tm = form['from_dttm'].time()
    to_dt = form['to_dttm'].date()
    to_tm = form['to_dttm'].time()

    worker_day_cashbox_detail = WorkerDayCashboxDetails.objects.select_related(
        'worker_day', 'on_cashbox'
    ).filter(
        worker_day__worker_shop_id=shop.id,
        worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
        worker_day__dt__gte=from_dt,
        worker_day__dt__lte=to_dt,
    )

    cashboxes_types = {x.id: x for x in CashboxType.objects.filter(shop=shop)}

    cashbox_type_ids = form['cashbox_type_ids']
    if len(cashbox_type_ids) > 0:
        worker_day_cashbox_detail = [x for x in worker_day_cashbox_detail if x.on_cashbox.type_id in cashbox_type_ids]

    users = {}
    for x in worker_day_cashbox_detail:
        worker_id = x.worker_day.worker_id
        if worker_id not in users:
            users[worker_id] = {
                'days': {},
                'cashbox_info': {}
            }
        user_item = users[worker_id]

        from_dt = x.worker_day.dt
        if from_dt not in user_item['days']:
            user_item['days'][from_dt] = {
                'day': x.worker_day,
                'details': []
            }

        user_item['days'][from_dt]['details'].append(x)

    users_ids = list(users.keys())
    for x in WorkerCashboxInfo.objects.filter(is_active=True, worker_id__in=users_ids):
        users[x.worker_id]['cashbox_info'][x.cashbox_type_id] = x

    today = datetime.now().date()
    response_users_ids = []
    for uid, user in users.items():
        if from_dt not in user['days']:
            continue

        day = user['days'][from_dt]['day']
        details = user['days'][from_dt]['details']

        cashbox = []
        for d in details:
            if d.tm_from < d.tm_to:
                if d.tm_from <= from_tm < d.tm_to:
                    cashbox.append(d)
            else:
                if d.tm_from <= from_tm or d.tm_to > from_tm:
                    cashbox.append(d)

        if len(cashbox) == 0:
            continue

        user['days'][from_dt]['details_one'] = cashbox[0]
        response_users_ids.append(uid)

        # if day.tm_break_start is not None:
        #     if datetime.combine(from_dt, day.tm_break_start) <= form['from_dttm'] < datetime.combine(from_dt, day.tm_break_start) + timedelta(hours=1):
        #         continue

        # cashbox_type = cashbox[0].on_cashbox.type_id
        # cashbox_info = user['cashbox_info'].get(cashbox_type)

    response = {
        'cashbox_types': {x.id: CashboxTypeConverter.convert(x) for x in cashboxes_types.values()},
        'users': {}
    }

    for x in User.objects.filter(id__in=response_users_ids):
        response['users'][x.id] = {
            'u': UserConverter.convert(x),
            'd': [],
            'c': []
        }

    # response = {
    #     'users': {
    #         uid: {
    #             'u': UserConverter.convert(u),
    #             'd': [WorkerDayConverter.convert(x) for x in days.get(u.id, [])],
    #             'c': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])]
    #         }
    #         for uid in response_users
    #     },
    #     'cashbox_types': {x.id: CashboxTypeConverter.convert(x) for x in cashbox_types}
    # }

    return JsonResponse.success(response)
