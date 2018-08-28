from datetime import datetime, time, timedelta
from collections import defaultdict

from django.http import HttpResponse
from django.db.models import Avg, Max

from src.db.models import (
    WorkerDay,
    User,
    CashboxType,
    WorkerCashboxInfo,
    WorkerDayCashboxDetails,
    PeriodDemand,
    WorkerDayChangeLog,
    Shop
)
from src.main.timetable.cashier_demand.forms import GetWorkersForm, GetCashiersTimetableForm
from src.util.collection import range_u, group_by
from src.util.models_converter import CashboxTypeConverter, UserConverter, WorkerDayConverter, WorkerCashboxInfoConverter, BaseConverter
from src.util.utils import api_method, JsonResponse
from src.util.forms import FormUtil
from src.conf.djconfig import QOS_DATETIME_FORMAT

from src.db.works.printer.run import run as get_xlsx
from dateutil.relativedelta import relativedelta

from ..utils import dttm_combine
from .utils import check_time_is_between_boarders, count_diff
import xlsxwriter
import io


@api_method('GET', GetCashiersTimetableForm)
def get_cashiers_timetable(request, form):
    shop_id = FormUtil.get_shop_id(request, form)

    if form['format'] == 'excel':
        def __file_name(__dt):
            return {
                1: 'January',
                2: 'February',
                3: 'March',
                4: 'April',
                5: 'May',
                6: 'June',
                7: 'Jule',
                8: 'August',
                9: 'September',
                10: 'October',
                11: 'November',
                12: 'December',
            }.get(__dt.month, 'Raspisanie')

        response = HttpResponse(content_type='application/force-download')
        response['Content-Disposition'] = 'attachment; filename={}.xlsx'.format(__file_name(form['from_dt']))
        response.write(get_xlsx(shop_id=shop_id, dt_from=form['from_dt']).read())
        return response

        # if shop.hidden_title == 'shop004':
        #     return redirect('/api/_i/media/timetable_temp/shop004.xlsx')

        # return JsonResponse.value_error('Excel is not supported yet')

    PERIOD_MINUTES = 30
    PERIOD_STEP = timedelta(minutes=PERIOD_MINUTES)
    TOTAL_PERIOD_SECONDS = PERIOD_STEP.total_seconds()

    # get data from db
    cashbox_types = CashboxType.objects.filter(shop_id=shop_id).order_by('id')
    if len(form['cashbox_type_ids']) > 0:
        cashbox_types = cashbox_types.filter(id__in=form['cashbox_type_ids'])
        if len(cashbox_types) != len(form['cashbox_type_ids']):
            return JsonResponse.value_error('bad cashbox_type_ids')

    cashbox_types = group_by(cashbox_types, group_key=lambda x: x.id)

    cashbox_types_main = []
    for cashbox_type in cashbox_types.values():
        if cashbox_type[0].is_main_type:
            cashbox_types_main.append(cashbox_type[0])
    cashbox_types_main = group_by(cashbox_types_main, group_key=lambda x: x.id)
    for ind in range(1, len(cashbox_types) - len(cashbox_types_main) + 1):
        cashbox_types_main[-ind] = None

    worker_day_cashbox_detail_filter = {
        'worker_day__worker_shop_id': shop_id,
        # worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
        'worker_day__dt__gte': form['from_dt'],
        'worker_day__dt__lte': form['to_dt'],
        'cashbox_type_id__in': cashbox_types.keys(),
        'dttm_to__isnull': False,
    }
    if form['position_id']:
        worker_day_cashbox_detail_filter['worker_day__worker__position__id'] = form['position_id']

    worker_day_cashbox_detail = WorkerDayCashboxDetails.objects.select_related(
        'worker_day',
    ).filter(
        **worker_day_cashbox_detail_filter
    ).exclude(
        status=WorkerDayCashboxDetails.TYPE_BREAK
    ).order_by(
        'worker_day__dt',
        'dttm_from',
        'dttm_to',
    )

    worker_cashbox_info = list(WorkerCashboxInfo.objects.filter(
        is_active=True,
        worker__workerday__dt__gte=form['from_dt'],
        worker__workerday__dt__lte=form['to_dt'],
        cashbox_type_id__in=cashbox_types.keys()
    ).distinct())

    mean_bills_per_step = WorkerCashboxInfo.objects.filter(
        is_active=True,
        cashbox_type_id__in=cashbox_types.keys()
    ).values('cashbox_type_id').annotate(speed_usual=Max('mean_speed'))
    mean_bills_per_step = {m['cashbox_type_id']: m['speed_usual'] for m in mean_bills_per_step}

    worker_amount = len(set([w.worker_id for w in worker_cashbox_info]))
    worker_cashbox_info = group_by(
        worker_cashbox_info,
        group_key=lambda x: (x.worker_id, x.cashbox_type_id)
    )

    period_demand = PeriodDemand.objects.filter(
        cashbox_type__shop_id=shop_id,
        dttm_forecast__gte=form['from_dt'],
        dttm_forecast__lte=form['to_dt'] + timedelta(days=1),
        type__in=[
            PeriodDemand.Type.LONG_FORECAST.value,
            PeriodDemand.Type.FACT.value,
        ],
        cashbox_type_id__in=cashbox_types.keys()
    ).order_by(
        'type',
        'dttm_forecast',
        'cashbox_type_id'
    )

    # supershop = SuperShop.objects.get(shop__id=shop_id)

    # init data
    real_cashiers = []
    predict_cashier_needs = []
    fact_cashier_needs = []
    lack_of_cashiers_on_period = []
    dttm_start = datetime.combine(form['from_dt'], time(3, 0))
    periods = 48
    # dttm_start = datetime.combine(form['from_dt'], supershop.tm_start) - PERIOD_STEP
    # periods = int(timediff(supershop.tm_start, supershop.tm_end) * 2 + 0.99999) + 5 # period 30 minutes

    time_borders = [
        [time(6, 30), time(12, 00), 'morning'],
        [time(18, 00), time(22, 30), 'evening'],
    ]

    ind_b = 0
    demand_ind = 0
    fact_ind = 0
    idle_time_numerator = 0
    idle_time_denominator = 0
    cashiers_lack_on_period_morning = []
    cashiers_lack_on_period_evening = []

    edge_ind = 0
    while (edge_ind < len(period_demand)) and (period_demand[edge_ind].type != PeriodDemand.Type.FACT.value):
        edge_ind += 1

    predict_demand = period_demand[:edge_ind]
    fact_demand = period_demand[edge_ind:]

    wdcds = worker_day_cashbox_detail  # alias
    wdcds_len = len(wdcds)

    for day_ind in range((form['to_dt'] - form['from_dt']).days):
        each_day_morning = []
        each_day_evening = []
        # cashiers_working_today = wdcds.filter(worker_day__dt=form['from_dt'] + timedelta(days=day_ind))
        for time_ind in range(periods):
            dttm = dttm_start + timedelta(days=day_ind) + time_ind * PERIOD_STEP

            dttm_end = dttm + PERIOD_STEP
            dttm_ind = dttm - PERIOD_STEP

            cashiers_on_cashbox_type = defaultdict(int)

            # cashier_working_now = []
            # for cashier in cashiers_working_today:
            #     if cashier.worker_day.tm_work_end > cashier.worker_day.tm_work_start:
            #         if cashier.worker_day.tm_work_start <= dttm.time() and cashier.worker_day.tm_work_end >= dttm_end.time():
            #             cashier_working_now.append(cashier)
            #     else:
            #         if cashier.worker_day.tm_work_start <= dttm.time():
            #             cashier_working_now.append(cashier)
            # todo: неправильно учитывается время от 23:30
            # for cashier in cashier_working_now:
            #     if cashier.cashbox_type is not None:
            #         cashiers_on_cashbox_type[cashier.cashbox_type.id] += 1  # shift to first model, which has intersection
            while (ind_b < wdcds_len) and (dttm_ind <= dttm) and wdcds[ind_b].dttm_to.time():
                dttm_ind = dttm_combine(wdcds[ind_b].worker_day.dt, wdcds[ind_b].dttm_to.time())
                ind_b += 1
            ind_b = ind_b - 1 if (dttm_ind > dttm) and ind_b else ind_b

            ind_e = ind_b
            period_bills = {i: 0 for i in cashbox_types.keys()}
            period_cashiers = 0.0
            period_cashiers_hard = 0.0
            if ind_e < wdcds_len and wdcds[ind_e].dttm_to.time():
                dttm_ind = dttm_combine(wdcds[ind_e].worker_day.dt, wdcds[ind_e].dttm_from.time())
                dttm_ind_end = dttm_combine(wdcds[ind_e].worker_day.dt, wdcds[ind_e].dttm_to.time())

            while (ind_e < wdcds_len) and (dttm_ind < dttm_end):
                if dttm_ind_end > dttm:
                    proportion = min(
                        (dttm_ind_end - dttm).total_seconds(),
                        (dttm_end - dttm_ind).total_seconds(),
                        TOTAL_PERIOD_SECONDS
                    ) / TOTAL_PERIOD_SECONDS
                    if wdcds[ind_e].worker_day.worker_id in worker_cashbox_info.keys():
                        period_bills[wdcds[ind_e].cashbox_type_id] += proportion *  \
                            (PERIOD_MINUTES / worker_cashbox_info[(wdcds[ind_e].worker_day.worker_id, wdcds[ind_e].cashbox_type_id)][0].mean_speed)
                    period_cashiers += 1 * proportion
                    if wdcds[ind_e].cashbox_type_id in cashbox_types_main.keys():
                        period_cashiers_hard += 1 * proportion

                ind_e += 1
                if ind_e < wdcds_len and wdcds[ind_e].dttm_to.time():
                    dttm_ind = dttm_combine(wdcds[ind_e].worker_day.dt, wdcds[ind_e].dttm_from.time())
                    dttm_ind_end = dttm_combine(wdcds[ind_e].worker_day.dt, wdcds[ind_e].dttm_to.time())

            dttm_converted = BaseConverter.convert_datetime(dttm)
            real_cashiers.append({
                'dttm': dttm_converted,
                'amount': period_cashiers
            })

            predict_diff_dict, demand_ind_2 = count_diff(dttm, predict_demand, demand_ind,  mean_bills_per_step, cashbox_types)
            predict_cashier_needs.append({
                'dttm': dttm_converted,
                'amount': sum(predict_diff_dict.values()), #+ period_cashiers,
            })

            real_diff_dict, fact_ind = count_diff(dttm, fact_demand, fact_ind,  mean_bills_per_step, cashbox_types)
            fact_cashier_needs.append({
                'dttm': dttm_converted,
                'amount': sum(real_diff_dict.values()), # + period_cashiers,
            })

            predict_diff_hard_dict, _ = count_diff(dttm, predict_demand, demand_ind, mean_bills_per_step, cashbox_types_main)
            if period_cashiers_hard > sum(predict_diff_hard_dict.values()):
                idle_time_numerator += period_cashiers_hard - sum(predict_diff_hard_dict.values())
            idle_time_denominator += period_cashiers_hard
            demand_ind = demand_ind_2

            need_amount_morning = 0
            need_amount_evening = 0
            need_total = 0

            for cashbox_type in cashbox_types:
                check_time = check_time_is_between_boarders(dttm.time(), time_borders)
                # if check_time == 'morning' or check_time == 'evening':
                    # if cashbox_type in predict_diff_dict.keys() \
                    #         and cashbox_type in cashiers_on_cashbox_type.keys()\
                    #         and predict_diff_dict[cashbox_type] > cashiers_on_cashbox_type.get(cashbox_type) \
                    #         and predict_diff_dict[cashbox_type] > 0:
                    #     if check_time == 'morning':
                    #         need_amount_morning += predict_diff_dict[cashbox_type] - cashiers_on_cashbox_type.get(cashbox_type)
                    #     elif check_time == 'evening':
                    #         need_amount_evening += predict_diff_dict[cashbox_type] - cashiers_on_cashbox_type.get(cashbox_type)
                    #     else:
                    #         pass
                if cashbox_type in cashbox_types_main.keys():
                    if check_time == 'morning':
                        need_amount_morning += predict_diff_dict.get(cashbox_type, 0)
                    elif check_time == 'evening':
                        need_amount_evening += predict_diff_dict.get(cashbox_type, 0)

                    need_total += predict_diff_dict.get(cashbox_type, 0)

            lack_of_cashiers_on_period.append({
                'lack_of_cashiers': max(0, need_total - period_cashiers_hard),
                'dttm_start': dttm_converted,
            })

            need_amount_morning = max(0, need_amount_morning - period_cashiers_hard)
            need_amount_evening = max(0, need_amount_evening - period_cashiers_hard)

            each_day_morning.append(need_amount_morning)
            each_day_evening.append(need_amount_evening)

        cashiers_lack_on_period_morning.append(max(each_day_morning))
        cashiers_lack_on_period_evening.append(max(each_day_evening))

    max_of_cashiers_lack_morning = max(cashiers_lack_on_period_morning)
    max_of_cashiers_lack_evening = max(cashiers_lack_on_period_evening)

    # total_lack_of_cashiers_on_period_demand = 0  # on all cashboxes types
    # if period_demand:
    #     prev_one_period_demand = period_demand[0]  # for first iteration
    #     for one_period_demand in period_demand:
    #         if one_period_demand.dttm_forecast == prev_one_period_demand.dttm_forecast:
    #             total_lack_of_cashiers_on_period_demand += one_period_demand.lack_of_cashiers
    #         else:
    #             lack_of_cashiers_on_period.append({
    #                 'lack_of_cashiers': total_lack_of_cashiers_on_period_demand,
    #                 'dttm_start': str(one_period_demand.dttm_forecast),
    #             })
    #             total_lack_of_cashiers_on_period_demand = one_period_demand.lack_of_cashiers
    #         prev_one_period_demand = one_period_demand

    changed_amount = WorkerDayChangeLog.objects.filter(
        worker_day__dt__gte = form['from_dt'],
        worker_day__dt__lte = form['to_dt'],
        worker_day__worker_shop_id=shop_id,
    ).count() // 11

    response = {
        'indicators': {
            'deadtime_part': round(100 * idle_time_numerator / (idle_time_denominator + 1e-8) , 1),
            'big_demand_persent': 0,  # big_demand_persent,
            'cashier_amount': worker_amount,  # len(users_amount_set),
            'FOT': None,
            'need_cashier_amount': round((max_of_cashiers_lack_morning + max_of_cashiers_lack_evening)), # * 1.4
            'change_amount': changed_amount,
        },
        'period_step': PERIOD_MINUTES,
        'tt_periods': {
            'real_cashiers': real_cashiers,
            'predict_cashier_needs': predict_cashier_needs,
            'fact_cashier_needs': fact_cashier_needs
        },
        'lack_of_cashiers_on_period': lack_of_cashiers_on_period
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
#xf
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

@api_method(
    'GET',
    GetWorkersForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def get_workers(request, form):
    shop = form['shop_id']

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
        worker_day_cashbox_detail = [x for x in worker_day_cashbox_detail if x.cashbox_type_id in cashbox_type_ids]

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
            if d.dttm_to.time() is None:
                if d.dttm_from.time() <= from_tm:
                    cashbox.append(d)
            elif d.dttm_from.time() < d.dttm_to.time():
                if d.dttm_from.time() <= from_tm < d.dttm_to.time():
                    cashbox.append(d)
            else:
                if d.dttm_from.time() <= from_tm or d.dttm_to.time() > from_tm:
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


@api_method('GET', GetCashiersTimetableForm)
def get_timetable_xlsx(request, form):
    shop = FormUtil.get_shop_id(request, form)
    dt_from = datetime(year=form['from_dt'].year, month=form['from_dt'].month, day=1)
    dt_to = dt_from + relativedelta(months=1) - timedelta(days=1)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()

    row = 6
    col = 5
    for user in User.objects.qos_filter_active(dt_from, dt_to, shop=shop).order_by('id'):
        worksheet.write(row, 0, "{} {} {}".format(user.last_name, user.first_name, user.middle_name))
        for i in range(dt_to.day):
            worksheet.write(row, col + 3 * i + 0, 'НД')
            worksheet.write(row, col + 3 * i + 1, 'НД')

        for wd in WorkerDay.objects.filter(worker=user, dt__gte=dt_from, dt__lte=dt_to).order_by('dt'):
            if wd.type == WorkerDay.Type.TYPE_HOLIDAY.value:
                cell_1 = 'В'
                cell_2 = 'В'
            elif wd.type == WorkerDay.Type.TYPE_VACATION.value:
                cell_1 = 'ОТ'
                cell_2 = 'ОТ'
            else:
                cell_1 = ''
                cell_2 = ''

            worksheet.write_string(row, col + 3 * int(wd.dt.day) - 3, cell_1)
            worksheet.write_string(row, col + 3 * int(wd.dt.day) - 2, cell_2)

        for wd in WorkerDayCashboxDetails.objects.select_related('cashbox_type', 'worker_day').filter(
                worker_day__worker=user,
                worker_day__dt__gte=dt_from,
                worker_day__dt__lte=dt_to
        ).order_by('worker_day__dt'):
            cell_1 = wd.worker_day.dttm_work_start.strftime(QOS_DATETIME_FORMAT)
            cell_2 = wd.worker_day.dttm_work_end.strftime(QOS_DATETIME_FORMAT)
            cell_3 = wd.cashbox_type.name

            worksheet.write_string(row, col + 3 * int(wd.worker_day.dt.day) - 3, cell_1)
            worksheet.write_string(row, col + 3 * int(wd.worker_day.dt.day) - 2, cell_2)
            worksheet.write_string(row, col + 3 * int(wd.worker_day.dt.day) - 1, cell_3)
        row += 1

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Timetable_{}.xlsx"'.format(
        BaseConverter.convert_date(dt_from))

    return response
