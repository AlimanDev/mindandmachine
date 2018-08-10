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
    Slot,
    UserWeekdaySlot,
    ProductionDay,
)
from src.util.collection import group_by
from src.util.forms import FormUtil
from src.util.models_converter import (
    TimetableConverter,
    CashboxTypeConverter,
    PeriodDemandConverter,
    UserConverter,
    WorkerConstraintConverter,
    WorkerCashboxInfoConverter,
    WorkerDayConverter,
    BaseConverter,
    ShopConverter,

    SlotConverter,
)
from src.util.utils import api_method, JsonResponse
from .forms import GetStatusForm, SetSelectedCashiersForm, CreateTimetableForm, DeleteTimetableForm, SetTimetableForm
import requests
from .utils import time2int
from ..table.utils import count_difference_of_normal_days


@api_method('GET', GetStatusForm)
def get_status(request, form):
    shop_id = FormUtil.get_shop_id(request, form)
    try:
        tt = Timetable.objects.get(shop_id=shop_id, dt=form['dt'])
    except Timetable.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    return JsonResponse.success(TimetableConverter.convert(tt))


@api_method(
    'POST',
    SetSelectedCashiersForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def set_selected_cashiers(request, form):
    shop = Shop.objects.get(id=form['shop_id'])
    User.objects.filter(shop=shop).exclude(id__in=form['cashier_ids']).update(auto_timetable=False)
    User.objects.filter(id__in=form['cashier_ids']).update(auto_timetable=True)
    return JsonResponse.success()


@api_method(
    'POST',
    CreateTimetableForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def create_timetable(request, form):
    shop_id = form['shop_id']
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
        collection=WorkerCashboxInfo.objects.select_related('cashbox_type').filter(cashbox_type__shop_id=shop_id, is_active=True),
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

    shop_dict = {
        'shop_type': shop.full_interface,
        'mean_queue_length': shop.mean_queue_length,
        'max_queue_length': shop.max_queue_length,
        'dead_time_part': shop.dead_time_part,
        'shop_count_lack': shop.count_lack,
    }

    cashboxes = [CashboxTypeConverter.convert(x, True) for x in
                 CashboxType.objects.filter(shop_id=shop_id, ).exclude(do_forecast=CashboxType.FORECAST_NONE)]


    users = User.objects.qos_filter_active(
        dt_from,
        dt_to,
        shop_id=shop_id,
        auto_timetable=True,
    )

    if shop.full_interface:
        lambda_func = lambda x: x.cashbox_type_id
        working_days = 22
    else:
        lambda_func = lambda x: periods[0].cashbox_type_id

        cashboxes = [{
            'id': periods[0].cashbox_type_id,
            'speed_coef': 1,
            'types_priority_weights': 1,
            'prob': 1,
            'prior_weight': 1,
            'prediction': 1,
        }]
        working_days = 20

    slots_all = group_by(
        collection=Slot.objects.filter(shop_id=shop_id),
        group_key=lambda_func,
    )

    slots_periods_dict = {k['id']: [] for k in cashboxes}
    for key, slots in slots_all.items():
        for slot in slots:
            # todo: temp fix for algo
            int_s = time2int(slot.tm_start, shop.forecast_step_minutes.minute, start_h=6)
            int_e = time2int(slot.tm_end, shop.forecast_step_minutes.minute, start_h=6)
            if int_s < int_e:
                slots_periods_dict[key].append([
                    time2int(slot.tm_start),
                    # BaseConverter.convert_time(slot.tm_start),
                    time2int(slot.tm_end),
                    # BaseConverter.convert_time(slot.tm_end),
                ])

    for cashbox in cashboxes:
        cashbox['slots'] = slots_periods_dict[cashbox['id']]
    extra_constr = {}

    # todo: this params should be in db

    if not shop.full_interface:

        # todo: fix trash constraints slots
        dttm_temp = datetime(2018, 1, 1, 0, 0)
        tms = [(dttm_temp + timedelta(seconds=i * 1800)).time() for i in range(48)]
        extra_constr = {}

        for user in users:
            constr = []
            user_weekdays_slots = UserWeekdaySlot.objects.select_related('slot').filter(worker=user)
            if len(user_weekdays_slots):
                user_slots = group_by(
                    collection=user_weekdays_slots,
                    group_key=lambda x: x.weekday
                )
                for day in range(7):
                    for tm in tms:
                        for slot in user_slots.get(day, []):
                            if tm >= slot.slot.tm_start and tm <= slot.slot.tm_end:
                                break
                        else:
                            constr.append({
                                'id': '',
                                'worker': user.id,
                                'weekday': day,
                                'tm': BaseConverter.convert_time(tm),
                            })
            extra_constr[user.id] = constr

    init_params = json.loads(shop.init_params)
    init_params['n_working_days_optimal'] = ProductionDay.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        type__in=ProductionDay.WORK_TYPES,
    ).count()

    user_info = count_difference_of_normal_days(dt_end=dt_from, usrs=users)

    data = {
        'start_dt': BaseConverter.convert_date(tt.dt),
        'IP': settings.HOST_IP,
        'timetable_id': tt.id,
        'forecast_step_minutes': shop.forecast_step_minutes.minute,
        'cashbox_types': cashboxes,
        # 'slots': slots_periods_dict,
        'shop': shop_dict,
        'shop_type': shop.full_interface, # todo: remove when change in algo
        'shop_count_lack': shop.count_lack, # todo: remove when change in algo
        'demand': [PeriodDemandConverter.convert(x) for x in periods],
        'cashiers': [
            {
                'general_info': UserConverter.convert(u),
                'constraints_info': [WorkerConstraintConverter.convert(x) for x in constraints.get(u.id, [])] + extra_constr.get(u.id, []),
                'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])],
                'workdays': [WorkerDayConverter.convert(x) for x in worker_day.get(u.id, [])],
                'prev_data': [WorkerDayConverter.convert(x) for x in prev_data.get(u.id, [])],
                'overworking_hours': user_info[u.id].get('diff_prev_paid_hours', 0),
                'overworking_days': user_info[u.id].get('diff_prev_paid_days', 0),
            }
            for u in users
        ],
        'algo_params': {
            'cost_weights': json.loads(shop.cost_weights),
            'method_params': json.loads(shop.method_params),
            'breaks_triplets': json.loads(shop.break_triplets),
            'init_params': init_params,
            # 'n_working_days_optimal': working_days, # Very kostil, very hot fix, we should take this param from proizvodstveny calendar'
        },
    }

    try:

        data = json.dumps(data).encode('ascii')
        # with open('./send_data_tmp.json', 'wb+') as f:
        #     f.write(data)
        req = urllib.request.Request('http://{}/'.format(settings.TIMETABLE_IP), data=data, headers={'content-type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            res = response.read().decode('utf-8')
        tt.task_id = json.loads(res).get('task_id', '')
        # print('\n\n\n\ {} \n\n\n'.format(tt.task_id))
        if tt.task_id is None:
            tt.status = Timetable.Status.ERROR.value
        tt.save()
    except Exception as e:
        print(e)
        tt.status = Timetable.Status.ERROR.value
        tt.save()
        JsonResponse.internal_error('Error sending data to server')
    return JsonResponse.success()


@api_method(
    'POST',
    DeleteTimetableForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def delete_timetable(request, form):
    shop_id = form['shop_id']

    dt_from = datetime(year=form['dt'].year, month=form['dt'].month, day=1)
    dt_now = datetime.now().date()

    if dt_from.date() < dt_now:
        return JsonResponse.value_error('Cannot delete past month')

    tts = Timetable.objects.filter(shop_id=shop_id, dt=dt_from)
    for tt in tts:
        if (tt.status == Timetable.Status.PROCESSING) and (not tt.task_id is None):
            try:
                requests.post(
                    'http://{}/delete_task'.format(settings.TIMETABLE_IP), data=json.dumps({'id': tt.task_id})
                )
            except (requests.ConnectionError, requests.ConnectTimeout):
                pass
    tts.delete()

    WorkerDayChangeLog.objects.filter(
        worker_day__worker_shop_id=shop_id,
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
        worker_day__worker__auto_timetable=True,
    ).filter(
        Q(worker_day__is_manual_tuning=False) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDayChangeRequest.objects.filter(
        worker_day__worker_shop_id=shop_id,
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
        worker_day__worker__auto_timetable=True,
    ).filter(
        Q(worker_day__is_manual_tuning=False) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDayCashboxDetails.objects.filter(
        worker_day__worker_shop_id=shop_id,
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
        worker_day__worker__auto_timetable=True,
    ).filter(
        Q(worker_day__is_manual_tuning=False) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDay.objects.filter(
        worker_shop_id=shop_id,
        dt__month=dt_from.month,
        dt__year=dt_from.year,
        worker__auto_timetable=True,
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
                # if wd['tm_break_start']:
                #     wd_obj.tm_break_start = BaseConverter.parse_time(wd['tm_break_start'])
                # else:
                #     wd_obj.tm_break_start = None

                wd_obj.save()
                WorkerDayCashboxDetails.objects.filter(worker_day=wd_obj).delete()
                wdd_list = []

                for wdd in wd['details']:
                    wdd_el = WorkerDayCashboxDetails(
                        worker_day=wd_obj,
                        tm_from=BaseConverter.parse_time(wdd['tm_from']),
                        tm_to=BaseConverter.parse_time(wdd['tm_to']),
                    )
                    if wdd['type'] > 0:
                        wdd_el.cashbox_type_id = wdd['type']
                    else:
                        wdd_el.status = WorkerDayCashboxDetails.TYPE_BREAK

                    wdd_list.append(wdd_el)
                WorkerDayCashboxDetails.objects.bulk_create(wdd_list)

            else:
                wd_obj.save()

    # update lack
    line = CashboxType.objects.filter(is_main_type=True, shop=timetable.shop_id)
    for str_dttm, lack in data['lack']:
        dttm = BaseConverter.convert_datetime(str_dttm)
        PeriodDemand.objects.update_or_create(
            lack_of_cashiers=lack,
            defaults={
                'dttm_forecast': dttm,
                'cashbox_type': line,
                'type': PeriodDemand.Type.LONG_FORECAST.value,
            })

    return JsonResponse.success()
