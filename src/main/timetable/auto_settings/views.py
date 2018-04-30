import json
import urllib.request

from datetime import datetime, timedelta

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

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
    User.objects.filter(id__in=form['cashier_ids']).update(auto_timetable=form['value'])
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
        type__in=[PeriodDemand.Type.LONG_FORECAST.value, PeriodDemand.Type.SHORT_FORECAST.value],
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
    if shop.full_interface:
        main_types = [
            'Линия',
            'Возврат',
            'Доставка',
            'Информация',
        ]

        special_types = [
            'Главная касса',
            'CЦ',
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
                'steps': 700,
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
                'CЦ': 1,
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
                'CЦ': 0,
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

    data = {
        'start_dt': BaseConverter.convert_date(tt.dt),
        'IP': '127.0.0.1:8000',
        'timetable_id': tt.id,
        'cashbox_types': cashboxes,
        'demand': [PeriodDemandConverter.convert(x) for x in periods],
        'cashiers': [
            {
                'general_info': UserConverter.convert(u),
                'constraints_info': [WorkerConstraintConverter.convert(x) for x in constraints.get(u.id, [])],
                'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])],
                'workdays': [WorkerDayConverter.convert(x) for x in worker_day.get(u.id, [])],
                'prev_data': [WorkerDayConverter.convert(x) for x in prev_data.get(u.id, [])],
            } for u in User.objects.filter(shop_id=shop_id)
        ],
        'algo_params': {
            'cost_weights': cost_weigths,
            'method_params': method_params,
        },
    }

    try:

        data = json.dumps(data).encode('ascii')
        with open('./send_data_tmp.json', 'wb+') as f:
            f.write(data)
        req = urllib.request.Request('http://127.0.0.1:5000/', data=data, headers={'content-type': 'application/json'})
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

    if dt_from < dt_now:
        return JsonResponse.value_error('Cannot delete past month')

    count, _ = Timetable.objects.filter(shop_id=shop_id, dt=dt_from).delete()

    if count > 1:
        return JsonResponse.internal_error(msg='too much deleted')
    elif count == 0:
        return JsonResponse.does_not_exists_error()

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
    if timetable.status != Timetable.Status.READY.value:
        return JsonResponse.success()

    users = {x.id: x for x in User.objects.filter(id__in=list(data['users']))}

    for uid, v in data['users'].items():
        for wd in v['workdays']:
            dt = BaseConverter.parse_date(wd['dt'])
            wd_type = WorkerDayConverter.parse_type(wd['type'])
            tm_work_start = BaseConverter.parse_time(wd['tm_work_start'])
            tm_work_end = BaseConverter.parse_time(wd['tm_work_end'])
            tm_break_start = BaseConverter.parse_time(wd['tm_break_start'])
            cashbox_type_id = wd['cashbox_type_id']

            try:
                wd_obj = WorkerDay.objects.get(worker_id=uid, dt=dt)

                try:
                    cd = WorkerDayCashboxDetails.objects.get(worker_day=wd_obj, tm_from=wd_obj.tm_work_start, tm_to=wd_obj.tm_work_end)
                    cd.on_cashbox_id = cashbox_type_id
                    cd.tm_from = tm_work_start
                    cd.tm_to = tm_work_end
                    cd.save()
                except WorkerDayCashboxDetails.DoesNotExist:
                    WorkerDayCashboxDetails.objects.create(
                        worker_day=wd_obj,
                        on_cashbox_id=cashbox_type_id,
                        tm_from=tm_work_start,
                        tm_to=tm_work_end
                    )
                except:
                    pass

                wd_obj.type = wd_type
                wd_obj.tm_work_start = tm_work_start
                wd_obj.tm_work_end = tm_work_end
                wd_obj.tm_break_start = tm_break_start
                wd_obj.save()
            except WorkerDay.DoesNotExist:
                wd_obj = WorkerDay.objects.create(
                    worker_id=uid,
                    dt=dt,
                    type=wd_type,
                    tm_work_start=tm_work_start,
                    tm_work_end=tm_work_end,
                    tm_break_start=tm_break_start,
                    worker_shop_id=users[uid].shop_id
                )
                cd = WorkerDayCashboxDetails.objects.create(
                    worker_day=wd_obj,
                    on_cashbox_id=cashbox_type_id,
                    tm_from=wd_obj.tm_work_start,
                    tm_to=wd_obj.tm_work_end
                )
            except:
                pass

    return JsonResponse.success()
