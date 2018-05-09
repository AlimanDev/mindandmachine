import json
import urllib.request

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q

from src.db.models import (
    Timetable,
    User,
    CashboxType,
    PeriodDemand,
    WorkerConstraint,
    WorkerCashboxInfo,
    WorkerDay,
    WorkerDayCashboxDetails,
    Shop,

    WorkerDayChangeLog,
    WorkerDayChangeRequest,
)
from src.util.collection import group_by
from src.util.forms import FormUtil
from src.util.models_converter import TimetableConverter, CashboxTypeConverter, PeriodDemandConverter, UserConverter, WorkerConstraintConverter, WorkerCashboxInfoConverter, \
    WorkerDayConverter, BaseConverter
from src.util.utils import api_method, JsonResponse
from .forms import GetStatusForm, SetSelectedCashiersForm, CreateTimetableForm, DeleteTimetableForm, SetTimetableForm


@api_method('GET', GetStatusForm)
def get_status(request, form):
    shop_id = FormUtil.get_shop_id(request, form)
    try:
        tt = Timetable.objects.get(shop_id=shop_id, dt=form['dt'])
    except Timetable.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    return JsonResponse.success(TimetableConverter.convert(tt))


@api_method('POST', SetSelectedCashiersForm)
def set_selected_cashiers(request, form):
    shop = Shop.objects.get(user__id=form['cashier_ids'][0])
    User.objects.filter(shop=shop).exclude(id__in=form['cashier_ids']).update(auto_timetable=False)
    User.objects.filter(id__in=form['cashier_ids']).update(auto_timetable=True)
    return JsonResponse.success()


@api_method('POST', CreateTimetableForm)
def create_timetable(request, form):
    shop_id = FormUtil.get_shop_id(request, form)
    dt_from = datetime(year=form['dt'].year, month=form['dt'].month, day=1)
    dt_to = dt_from + relativedelta(months=1) - timedelta(days=1)

    try:
        tt = Timetable.objects.create(
            shop_id=shop_id,
            dt=dt_from,
            status=Timetable.Status.PROCESSING.value,
            dttm_status_change=datetime.now()
        )
    except:
        return JsonResponse.already_exists_error()

    periods = PeriodDemand.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type=PeriodDemand.Type.LONG_FORECAST.value,
        dttm_forecast__date__gte=dt_from,
        dttm_forecast__date__lte=dt_to
    )

    constraints = group_by(
        collection=WorkerConstraint.objects.select_related('worker').filter(worker__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )

    # todo: tooooo slow
    worker_cashbox_info = group_by(
        collection=WorkerCashboxInfo.objects.select_related('cashbox_type').filter(cashbox_type__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )

    worker_day = group_by(
        collection=WorkerDay.objects.filter(worker_shop_id=shop_id, dt__gte=dt_from, dt__lte=dt_to),
        group_key=lambda x: x.worker_id
    )

    prev_data = group_by(
        collection=WorkerDay.objects.filter(worker_shop_id=shop_id, dt__gte=dt_from - timedelta(days=7), dt__lt=dt_from),
        group_key=lambda x: x.worker_id
    )

    shop = Shop.objects.get(id=shop_id)
    cashboxes = [CashboxTypeConverter.convert(x) for x in CashboxType.objects.filter(shop_id=shop_id)]

    cost_weigths = {}
    method_params = {}

    # todo: this params should be in db
    if shop.full_interface:
        main_types = [
            'Линия',
            'Возврат',
            'Доставка',
            'Информация',
        ]

        special_types = [
            'Главная касса',
            'СЦ',
            'ОРКК',
            'Сверка',
        ]

        cost_weigths = {
            'F': 1,
            '40hours': 0,
            'days': 2*10**2,
            '15rest': 10**4,
            '5d': 10**4,
            'hard': 10,
            'soft': 0,
            'overwork_fact_days': 3*10**6,
            'F_bills_coef': 3,
            'diff_days_coef': 1,
            'solitary_days': 5*10**5,
            'holidays': 3*10**5, #3*10**5,# 2*10**6,
            'zero_cashiers': 3,
            'slots': 2*10**7,
            'too_much_days': 22,
        }

        method_params = [
            {
                'steps': 100,
                'select_best': 8,
                'changes': 10,
                'variety': 8,
                'days_change_prob': 0.05,
                'periods_change_prob': 0.55,
                'add_day_prob': 0.33,
                'del_day_prob': 0.33
            },
            {
                'steps': 2000,
                'select_best': 8,
                'changes': 30,
                'variety': 8,
                'days_change_prob': 0.33,
                'periods_change_prob': 0.33,
                'add_day_prob': 0.33,
                'del_day_prob': 0.33
            },

        ]

        probs = {}
        prior_weigths = {}
        slots = {}
        if shop.super_shop.code == '003':
            probs = {
                'Линия': 3,
                'Возврат': 0.5,
                'Доставка': 1,
                'Информация': 0.2,
                'Главная касса': 5,
                'СЦ': 1,
                'ОРКК': 3.5,
                'Сверка': 10,
            }

            slots = {
                'Главная касса': [(0, 36), (20, 56), (40, 76)],
                'ОРКК': [(8, 44), (36, 72)],
                'СЦ': [(8, 44), (36, 72)],
                'Сверка': [(12, 48)],
            }
            prior_weigths ={
                'Линия': 1.5,
                'Возврат': 15,
                'Доставка': 10,
                'Информация': 30,
                'Главная касса': 0,
                'СЦ': 0,
                'ОРКК': 0,
                'Сверка': 0,
            }
        elif shop.super_shop.code == '004':
            probs = {
                'Линия': 3,
                'Возврат': 0.5,
                'Доставка': 1,
                'Информация': 0.2,
                'Главная касса': 3,
            }

            slots = {
                'Главная касса': [(2, 38), (38, 74)],
            }
            prior_weigths = {
                'Линия': 1.5,
                'Возврат': 15,
                'Доставка': 10,
                'Информация': 30,
                'Главная касса': 2000,
            }

        for cashbox in cashboxes:
            if cashbox['name'] in main_types:
                cashbox['prediction'] = 1
            elif cashbox['name'] in special_types:
                cashbox['prediction'] = 2
            else:
                cashbox['prediction'] = 0
            if cashbox['prediction']:
                cashbox['prob'] = probs[cashbox['name']]
            else:
                cashbox['prob'] = 0
            cashbox['slots'] = slots.get(cashbox['name'], [])
            cashbox['prior_weight'] = prior_weigths.get(cashbox['name'], 1)
    else:
        cost_weigths = {
            'F': 1,
            '40hours': 0,
            'days': 100,
            '15rest': 0,
            '5d': 0,
            'hard': 0,
            'soft': 0,
            'overwork_fact_days': 3 * 10 ** 4,
            'F_bills_coef': 3,
            'diff_days_coef': 1,
            'solitary_days': 5 * 10 ** 4,
            'holidays': 10 ** 3,  # 3*10**5,# 2*10**6,
            'zero_cashiers': 0,
            'slots': 0,  # 2*10**3,
        }
        method_params = [{
            'steps': 200,
            'select_best':8,
            'changes': 5,
            'variety': 8,
            'days_change_prob': 0.5,
            'periods_change_prob': 0.5,
            'add_day_prob': 0.33,
            'del_day_prob': 0.33,
        }]
        slots_periods_dict = []
        if shop.title == 'Сантехника':
            slots_periods_dict = [(4, 40), (20, 56), (36, 72)]
        elif shop.title == 'Декор':
            slots_periods_dict = [(4, 40), (12, 48), (28, 64), (36, 72), (4, 52)]
        elif shop.title == 'Электротовары':
            slots_periods_dict = [(4, 40), (8, 44), (28, 64), (36, 72), (16, 52), (28, 64)]

        cashboxes = [{
            'id': periods[0].cashbox_type_id,
            'slots': slots_periods_dict,
            'speed_coef': 1,
            'types_priority_weights': 1,
            'prob': 1,
            'prior_weight': 1,
            'prediction': 1,
        }]

        # todo: send slots to server

    data = {
        'start_dt': BaseConverter.convert_date(tt.dt),
        'IP': settings.HOST_IP,
        'timetable_id': tt.id,
        'cashbox_types': cashboxes,
        'shop_type': shop.full_interface,
        'demand': [PeriodDemandConverter.convert(x) for x in periods],
        'cashiers': [
            {
                'general_info': UserConverter.convert(u),
                'constraints_info': [WorkerConstraintConverter.convert(x) for x in constraints.get(u.id, [])],
                'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])],
                'workdays': [WorkerDayConverter.convert(x) for x in worker_day.get(u.id, [])],
                'prev_data': [WorkerDayConverter.convert(x) for x in prev_data.get(u.id, [])],
            } for u in User.objects.filter(shop_id=shop_id, auto_timetable=True)
        ],
        'algo_params': {
            'cost_weights': cost_weigths,
            'method_params': method_params,
        },
    }

    try:

        data = json.dumps(data).encode('ascii')
        # with open('./send_data_tmp.json', 'wb+') as f:
        #     f.write(data)
        req = urllib.request.Request('http://{}/'.format(settings.TIMETABLE_IP), data=data, headers={'content-type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            data = response.read().decode('utf-8')
    except:
        JsonResponse.internal_error('Error sending data to server')
    return JsonResponse.success()


@api_method('POST', DeleteTimetableForm)
def delete_timetable(request, form):
    shop_id = FormUtil.get_shop_id(request, form)

    dt_from = datetime(year=form['dt'].year, month=form['dt'].month, day=1)
    dt_now = datetime.now().date()

    if dt_from.date() < dt_now:
        return JsonResponse.value_error('Cannot delete past month')

    count, _ = Timetable.objects.filter(shop_id=shop_id, dt=dt_from).delete()

    WorkerDayChangeLog.objects.filter(
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
    ).filter(
        Q(worker_day__is_manual_tuning=False) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDayChangeRequest.objects.filter(
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
    ).filter(
        Q(worker_day__is_manual_tuning=False) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDayCashboxDetails.objects.filter(
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
    ).filter(
        Q(worker_day__is_manual_tuning=False) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDay.objects.filter(
        dt__month=dt_from.month,
        dt__year=dt_from.year,
        is_manual_tuning=False,
    ).filter(
        Q(is_manual_tuning=False) |
        Q(type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    # if count > 1:
    #     return JsonResponse.internal_error(msg='too much deleted')
    # elif count == 0:
    #     return JsonResponse.does_not_exists_error()

    return JsonResponse.success()


@csrf_exempt
@api_method('POST', SetTimetableForm, auth_required=False)
def set_timetable(request, form):
    if settings.QOS_SET_TIMETABLE_KEY is None:
        return JsonResponse.internal_error('key is not configured')

    if form['key'] != settings.QOS_SET_TIMETABLE_KEY:
        return JsonResponse.internal_error('invalid key')

    try:
        data = json.loads(form['data'])
    except:
        return JsonResponse.internal_error('cannot parse json')

    try:
        timetable = Timetable.objects.get(id=data['timetable_id'])
    except Timetable.DoesNotExist:
        return JsonResponse.does_not_exists_error('timetable')

    timetable.status = TimetableConverter.parse_status(data['timetable_status'])
    timetable.save()
    if timetable.status != Timetable.Status.READY.value:
        return JsonResponse.success()

    users = {x.id: x for x in User.objects.filter(id__in=list(data['users']))}

    for uid, v in data['users'].items():
        for wd in v['workdays']:
            # todo: actually use a form here is better
            # todo: too much request to db

            dt = BaseConverter.parse_date(wd['dt'])
            try:
                wd_obj = WorkerDay.objects.get(worker_id=uid, dt=dt)
                if wd_obj.is_manual_tuning or wd_obj.type != WorkerDay.Type.TYPE_EMPTY:
                    continue
            except WorkerDay.DoesNotExist:
                wd_obj = WorkerDay(
                    dt=BaseConverter.parse_date(wd['dt']),
                    worker_id=uid,

                )

            wd_obj.worker_shop_id=users[int(uid)].shop_id
            wd_obj.type = WorkerDayConverter.parse_type(wd['type'])
            if WorkerDay.is_type_with_tm_range(wd_obj.type):
                wd_obj.tm_work_start = BaseConverter.parse_time(wd['tm_work_start'])
                wd_obj.tm_work_end = BaseConverter.parse_time(wd['tm_work_end'])
                if wd['tm_break_start']:
                    wd_obj.tm_break_start = BaseConverter.parse_time(wd['tm_break_start'])
                else:
                    wd_obj.tm_break_start = None

                wd_obj.save()
                WorkerDayCashboxDetails.objects.filter(worker_day=wd_obj).delete()
                WorkerDayCashboxDetails.objects.create(
                    worker_day=wd_obj,
                    on_cashbox_id=wd['cashbox_type_id'],
                    tm_from=wd_obj.tm_work_start,
                    tm_to=wd_obj.tm_work_end
                )
            else:
                wd_obj.save()

            # wd_type = WorkerDayConverter.parse_type(wd['type'])
            # tm_work_start = BaseConverter.parse_time(wd['tm_work_start'])
            # tm_work_end = BaseConverter.parse_time(wd['tm_work_end'])
            # tm_break_start = BaseConverter.parse_time(wd['tm_break_start'])
            # cashbox_type_id = wd['cashbox_type_id']
            #
            # try:
            #     wd_obj = WorkerDay.objects.get(worker_id=uid, dt=dt)
            #
            #     try:
            #         cd = WorkerDayCashboxDetails.objects.get(worker_day=wd_obj, tm_from=wd_obj.tm_work_start, tm_to=wd_obj.tm_work_end)
            #         cd.on_cashbox_id = cashbox_type_id
            #         cd.tm_from = tm_work_start
            #         cd.tm_to = tm_work_end
            #         cd.save()
            #     except WorkerDayCashboxDetails.DoesNotExist:
            #         WorkerDayCashboxDetails.objects.create(
            #             worker_day=wd_obj,
            #             on_cashbox_id=cashbox_type_id,
            #             tm_from=tm_work_start,
            #             tm_to=tm_work_end
            #         )
            #     # except:
            #     #     pass
            #
            #     wd_obj.type = wd_type
            #     wd_obj.tm_work_start = tm_work_start
            #     wd_obj.tm_work_end = tm_work_end
            #     wd_obj.tm_break_start = tm_break_start
            #     wd_obj.save()
            # except WorkerDay.DoesNotExist:
            #     wd_obj = WorkerDay.objects.create(
            #         worker_id=uid,
            #         dt=dt,
            #         type=wd_type,
            #         tm_work_start=tm_work_start,
            #         tm_work_end=tm_work_end,
            #         tm_break_start=tm_break_start,
            #         worker_shop_id=users[uid].shop_id
            #     )
            #     cd = WorkerDayCashboxDetails.objects.create(
            #         worker_day=wd_obj,
            #         on_cashbox_id=cashbox_type_id,
            #         tm_from=wd_obj.tm_work_start,
            #         tm_to=wd_obj.tm_work_end
            #     )
            # except:
            #     pass
    return JsonResponse.success()
