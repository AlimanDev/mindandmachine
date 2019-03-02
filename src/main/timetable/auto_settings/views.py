import json
import urllib.request

from datetime import datetime, timedelta, date, time

from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Avg

from src.db.models import (
    Timetable,
    User,
    WorkType,
    OperationType,
    PeriodClients,
    WorkerConstraint,
    WorkerCashboxInfo,
    WorkerDay,
    WorkerDayCashboxDetails,
    Shop,
    WorkerDayChangeRequest,
    Slot,
    UserWeekdaySlot,
    ProductionDay,
)
from src.util.collection import group_by
from src.util.forms import FormUtil
from src.util.models_converter import (
    TimetableConverter,
    WorkTypeConverter,
    UserConverter,
    WorkerConstraintConverter,
    WorkerCashboxInfoConverter,
    WorkerDayConverter,
    BaseConverter,
    PeriodClientsConverter,
)
from src.util.utils import api_method, JsonResponse
from .forms import (
    GetStatusForm,
    SetSelectedCashiersForm,
    CreateTimetableForm,
    DeleteTimetableForm,
    SetTimetableForm,
)
import requests
from ..table.utils import count_difference_of_normal_days
from src.main.other.notification.utils import send_notification
from django.db.models import F
from calendar import monthrange


@api_method('GET', GetStatusForm)
def get_status(request, form):
    """
    Возвращает статус расписания на данный месяц

    Args:
        method: GET
        url: /api/timetable/auto_setting/get_status
        shop_id(int): required = False
        dt(QOS_DATE): required = True

    Returns:
        {
            'id': id расписания,
            'shop': int,
            'dt': дата расписания,
            'status': статус расписания,
            'dttm_status_change': дата изменения
        }
    """
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
    """
    Проставляет поле auto_timetable = value у заданных сотрудников

    Args:
        method: POST
        url: /api/timetable/auto_settings/set_selected_cashiers
        cashier_ids(list): id'шники сотрудников которым проставлять
        shop_id(int): required = True

    Note:
        Всем другим сотрудникам из этого магаза проставляется значение противоположное value
    """
    shop_workers = User.objects.filter(shop_id=form['shop_id'], attachment_group=User.GROUP_STAFF)
    shop_workers.exclude(id__in=form['cashier_ids']).update(auto_timetable=False)
    User.objects.filter(id__in=form['cashier_ids']).update(auto_timetable=True)
    return JsonResponse.success()


@api_method(
    'POST',
    CreateTimetableForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def create_timetable(request, form):
    """
    Создает request на qos_algo с заданным параметрами

    Args:
        method: POST
        url: /api/timetable/auto_settings/create_timetable
        shop_id(int): required = True
        dt(QOS_DATE): required = True

    Raises:
        JsonResponse.internal_error: если ошибка при составлении расписания

    Note:
        Отправляет уведомление о том, что расписание начало составляться
    """
    shop_id = form['shop_id']
    dt_from = datetime(year=form['dt'].year, month=form['dt'].month, day=1).date()
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

    users = User.objects.qos_filter_active(
        dt_from,
        dt_to,
        shop_id=shop_id,
        auto_timetable=True,
    )
    shop = Shop.objects.get(id=shop_id)
    period_step = shop.forecast_step_minutes.hour * 60 + shop.forecast_step_minutes.minute
    super_shop = shop.super_shop

    # проверка что у всех юзеров указаны специализации
    users_without_spec = []
    for u in users:
        worker_cashbox_info = WorkerCashboxInfo.objects.filter(worker=u).values_list('is_active')
        if not [wci_obj for wci_obj in worker_cashbox_info if True in wci_obj]:
            users_without_spec.append(u.first_name + ' ' + u.last_name)
    if users_without_spec:
        # tt.status = Timetable.Status.ERROR.value
        status_message = 'У пользователей {} не проставлены специалации.'.format(', '.join(users_without_spec))
        tt.delete()
        return JsonResponse.value_error(status_message)

    # проверка что есть спрос на период
    period_difference = {'work_type_name': [], 'difference': []}
    period_normal_count = (round((datetime.combine(date.today(), super_shop.tm_end) -
                                  datetime.combine(date.today(), super_shop.tm_start)).seconds/3600) * 2 + 1 - 1) * \
                          ((dt_to - dt_from).days + 1)
    work_types = WorkType.objects.filter(shop_id=shop_id)
    for work_type in work_types:
        periods = PeriodClients.objects.filter(
            operation_type__work_type=work_type,
            type=PeriodClients.LONG_FORECASE_TYPE,
            dttm_forecast__date__gte=dt_from,
            dttm_forecast__date__lt=dt_to + timedelta(days=1),
        ).exclude(
            dttm_forecast__time=time(0, 0),
        ).annotate(
            clients=F('value') / (period_step / F('operation_type__speed_coef')) * (1.0 + shop.absenteeism)
        )
        if periods.count() != period_normal_count:
            period_difference['work_type_name'].append(work_type.name)
            period_difference['difference'].append(abs(period_normal_count - periods.count()))
    if period_difference['work_type_name']:
        status_message = 'На типе работ {} не хватает объектов спроса {}.'.format(
            ', '.join(period_difference['work_type_name']),
            ', '.join(str(x) for x in period_difference['difference'])
        )
        tt.delete()
        return JsonResponse.value_error(status_message)

    periods = PeriodClients.objects.select_related(
        'operation_type__work_type'
    ).filter(
        operation_type__work_type__shop_id=shop_id,
        type=PeriodClients.LONG_FORECASE_TYPE,
        dttm_forecast__date__gte=dt_from,
        dttm_forecast__date__lte=dt_to,
    ).exclude(
        dttm_forecast__time=time(0, 0)
    )

    constraints = group_by(
        collection=WorkerConstraint.objects.select_related('worker').filter(worker__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )

    # todo: tooooo slow
    worker_cashbox_info = group_by(
        collection=WorkerCashboxInfo.objects.select_related('work_type').filter(work_type__shop_id=shop_id, is_active=True),
        group_key=lambda x: x.worker_id
    )

    worker_day = group_by(
        collection=WorkerDay.objects.qos_current_version().select_related('worker').filter(
            worker__shop_id=shop_id,
            dt__gte=dt_from,
            dt__lte=dt_to,
        ),
        group_key=lambda x: x.worker_id
    )

    prev_data = group_by(
        collection=WorkerDay.objects.qos_current_version().select_related('worker').filter(
            worker__shop_id=shop_id,
            dt__gte=dt_from - timedelta(days=7),
            dt__lt=dt_from,
        ),
        group_key=lambda x: x.worker_id
    )

    if shop.process_type == Shop.YEAR_NORM:
        max_work_coef = (1 + shop.more_norm / 100)
        min_work_coef = (1 - shop.less_norm / 100)
    else:
        max_work_coef = 1
        min_work_coef = 1

    shop_dict = {
        # 'shop_type': shop.full_interface,
        'mean_queue_length': shop.mean_queue_length,
        'max_queue_length': shop.max_queue_length,
        'dead_time_part': shop.dead_time_part,
        # 'shop_count_lack': shop.count_lack,
        'max_work_coef': max_work_coef,
        'min_work_coef': min_work_coef,
        'period_step': shop.forecast_step_minutes.minute,
        'tm_start_work': BaseConverter.convert_time(shop.tm_shop_opens),
        'tm_end_work': BaseConverter.convert_time(shop.tm_shop_closes),
        'min_work_period': shop.shift_start * 60,
        'max_work_period': shop.shift_end * 60,
        'tm_lock_start': list(map(lambda x: x + ':00', json.loads(shop.restricted_start_times))),
        'tm_lock_end': list(map(lambda x: x + ':00', json.loads(shop.restricted_end_times))),
        'hours_between_slots': shop.min_change_time,
        'morning_evening_same': shop.even_shift_morning_evening,
        'workdays_holidays_same': False, #TODO(as): флаг, учитывать ли равномерность по работе чуваков в будни и выхи при составлении (нет на фронте)
        '1day_holiday': int(shop.exit1day),
        # 'paired_weekday': shop.paired_weekday,
        'max_outsourcing_day': 3,
    }

    cashboxes = [
        WorkTypeConverter.convert(x) for x in WorkType.objects.filter(
            shop_id=shop_id
        ).exclude(
            work_type_reversed__do_forecast=OperationType.FORECAST_NONE
        )
    ]

    slots_all = group_by(
        collection=Slot.objects.filter(shop_id=shop_id),
        group_key=lambda x: x.work_type_id,
    )

    slots_periods_dict = {k['id']: [] for k in cashboxes}
    for key, slots in slots_all.items():
        for slot in slots:
            # todo: temp fix for algo
            # int_s = time2int(slot.tm_start, shop.forecast_step_minutes.minute, start_h=6)
            # int_e = time2int(slot.tm_end, shop.forecast_step_minutes.minute, start_h=6)
            # if int_s < int_e:
                slots_periods_dict[key].append({
                    # time2int(slot.tm_start),
                    'tm_start': BaseConverter.convert_time(slot.tm_start),
                    # time2int(slot.tm_end),
                    'tm_end': BaseConverter.convert_time(slot.tm_end),
            })

    for cashbox in cashboxes:
        cashbox['slots'] = slots_periods_dict[cashbox['id']]
    extra_constr = {}

    # todo: add UserWeekdaySlot
    # if not shop.full_interface:
    #     # todo: fix trash constraints slots
    #     dttm_temp = datetime(2018, 1, 1, 0, 0)
    #     tms = [(dttm_temp + timedelta(seconds=i * 1800)).time() for i in range(48)]
    #     extra_constr = {}
    #
    #     for user in users:
    #         constr = []
    #         user_weekdays_slots = UserWeekdaySlot.objects.select_related('slot').filter(worker=user)
    #         if len(user_weekdays_slots):
    #             user_slots = group_by(
    #                 collection=user_weekdays_slots,
    #                 group_key=lambda x: x.weekday
    #             )
    #             for day in range(7):
    #                 for tm in tms:
    #                     for slot in user_slots.get(day, []):
    #                         if tm >= slot.slot.tm_start and tm <= slot.slot.tm_end:
    #                             break
    #                     else:
    #                         constr.append({
    #                             'id': '',
    #                             'worker': user.id,
    #                             'weekday': day,
    #                             'tm': BaseConverter.convert_time(tm),
    #                         })
    #         extra_constr[user.id] = constr

    init_params = json.loads(shop.init_params)
    init_params['n_working_days_optimal'] = ProductionDay.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        type__in=ProductionDay.WORK_TYPES,
    ).count()

    user_info = count_difference_of_normal_days(dt_end=dt_from, usrs=users)

    prev_month_num = (dt_from - timedelta(days=1)).month
    year_num = (dt_from - timedelta(days=1)).year
    prev_days_amount = monthrange(year_num, prev_month_num)[1]

    prev_month_data = group_by(
        collection=WorkerDay.objects.qos_current_version().select_related('worker').filter(
            worker__shop_id=shop_id,
            dt__gte=dt_from - timedelta(days=prev_days_amount),
            dt__lt=dt_from,
        ),
        group_key=lambda x: x.worker_id,
    )

    # shop.paired_weekday = True
    resting_states_list = [WorkerDay.Type.TYPE_HOLIDAY.value]
    if shop.paired_weekday:
        for user in users:
            coupled_weekdays = 0
            month_info = sorted(prev_month_data.get(user.id, []), key=lambda x: x.dt)
            for day in range(len(month_info) - 1):
                day_info = month_info[day]
                if day_info.dt.weekday() == 5 and day_info.type in resting_states_list:
                    next_day_info = month_info[day + 1]
                    if next_day_info.dt.weekday() == 6 and next_day_info.type in resting_states_list:
                        coupled_weekdays += 1

            user_info[user.id]['required_coupled_hol_in_hol'] = 0 if coupled_weekdays else 1
            # print(user_info[user.id]['required_coupled_hol_in_hol'])

    # mean_bills_per_step = WorkerCashboxInfo.objects.filter(
    #     is_active=True,
    #     work_type__shop_id=shop_id,
    # ).values('work_type_id').annotate(speed_usual=Avg('mean_speed'))
    # mean_bills_per_step = {m['work_type_id']: 30 / m['speed_usual'] for m in mean_bills_per_step}

    cashboxes_dict = {cb['id']: cb for cb in cashboxes}

    demands = [PeriodClientsConverter.convert(x) for x in periods]
    # for demand in demands:
    #     demand['clients'] = demand['clients'] / (period_step / cashboxes_dict[demand['work_type']]['speed_coef'])
    #     # if cashboxes_dict[demand['work_type']]['do_forecast'] == WorkType.FORECAST_LITE:
    #     demand['clients'] = 1


    data = {
        # 'start_dt': BaseConverter.convert_date(tt.dt),
        'IP': settings.HOST_IP,
        'timetable_id': tt.id,
        'forecast_step_minutes': shop.forecast_step_minutes.minute,
        'work_types': cashboxes,
        # 'slots': slots_periods_dict,
        'shop': shop_dict,
        # 'shop_type': shop.full_interface, # todo: remove when change in algo
        # 'shop_count_lack': shop.count_lack, # todo: remove when change in algo
        'demand': demands,
        'cashiers': [
            {
                'general_info': UserConverter.convert(u),
                'constraints_info': [WorkerConstraintConverter.convert(x) for x in constraints.get(u.id, [])] + extra_constr.get(u.id, []),
                'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])],
                'workdays': [WorkerDayConverter.convert(x) for x in worker_day.get(u.id, [])],
                'prev_data': [WorkerDayConverter.convert(x) for x in prev_data.get(u.id, [])],
                'overworking_hours': user_info[u.id].get('diff_prev_paid_hours', 0),
                'overworking_days': user_info[u.id].get('diff_prev_paid_days', 0),
                # 'norm_work_amount': 160, #TODO (as)
                'required_coupled_hol_in_hol': user_info[u.id].get('required_coupled_hol_in_hol', 0)
            }
            for u in users
        ],
        'algo_params': {
            'min_add_coef': shop.mean_queue_length,
            'cost_weights': json.loads(shop.cost_weights),
            'method_params': json.loads(shop.method_params),
            'breaks_triplets': json.loads(shop.break_triplets),
            'init_params': init_params,
            # 'n_working_days_optimal': working_days, # Very kostil, very hot fix, we should take this param from proizvodstveny calendar'
        },
    }

    tt.save()
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
        tt.status_message = str(e)
        tt.save()
        JsonResponse.internal_error('Error sending data to server')

    send_notification('C', tt, sender=request.user)
    return JsonResponse.success()


@api_method(
    'POST',
    DeleteTimetableForm,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def delete_timetable(request, form):
    """
    Удаляет расписание на заданный месяц. Также отправляет request на qos_algo на остановку задачи в селери

    Args:
        method: POST
        url: /api/timetable/auto_settings/delete_timetable
        shop_id(int): required = True
        dt(QOS_DATE): required = True

    Note:
        Отправляет уведомление о том, что расписание было удалено
    """
    shop_id = form['shop_id']

    dt_from = datetime(year=form['dt'].year, month=form['dt'].month, day=1)
    dt_now = datetime.now().date()

    # if dt_from.date() < dt_now:
    #     return JsonResponse.value_error('Cannot delete past month')

    tts = Timetable.objects.filter(shop_id=shop_id, dt=dt_from)
    for tt in tts:
        if (tt.status == Timetable.Status.PROCESSING.value) and (not tt.task_id is None):
            try:
                requests.post(
                    'http://{}/delete_task'.format(settings.TIMETABLE_IP), data=json.dumps({'id': tt.task_id}).encode('ascii')
                )
            except (requests.ConnectionError, requests.ConnectTimeout):
                pass
            send_notification('D', tt, sender=request.user)
    tts.delete()

    WorkerDayChangeRequest.objects.select_related('worker_day', 'worker_day__worker').filter(
        worker__shop_id=shop_id,
        dt__month=dt_from.month,
        dt__year=dt_from.year,
        worker__auto_timetable=True,
    ).delete()

    WorkerDayCashboxDetails.objects.select_related('worker_day', 'worker_day__worker').filter(
        worker_day__worker__shop_id=shop_id,
        worker_day__dt__month=dt_from.month,
        worker_day__dt__year=dt_from.year,
        worker_day__worker__auto_timetable=True,
    ).filter(
        Q(worker_day__created_by__isnull=True) |
        Q(worker_day__type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    WorkerDay.objects.select_related('worker').filter(
        worker__shop_id=shop_id,
        dt__month=dt_from.month,
        dt__year=dt_from.year,
        worker__auto_timetable=True,
    ).filter(
        Q(created_by__isnull=True) |
        Q(type=WorkerDay.Type.TYPE_EMPTY.value)
    ).delete()

    return JsonResponse.success()


@csrf_exempt
@api_method('POST', SetTimetableForm, auth_required=False)
def set_timetable(request, form):
    """
    Ждет request'a от qos_algo. Когда получает, записывает данные по расписанию в бд

    Args:
        method: POST
        url: /api/timetable/auto_settings/set_timetable
        key(str): ключ для сверки
        data(str): json data с данными от qos_algo

    Raises:
        JsonResponse.internal_error: если ключ не сконфигурирован, либо не подходит
        JsonResponse.does_not_exists_error: если расписания нет в бд

    Note:
        Отправляет уведомление о том, что расписание успешно было создано
    """
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
    timetable.status_message = data.get('status_message', False)
    timetable.save()
    if timetable.status != Timetable.Status.READY.value and timetable.status_message:
        return JsonResponse.success(timetable.status_message)
    users = {x.id: x for x in User.objects.filter(id__in=list(data['users']), attachment_group=User.GROUP_STAFF)}

    for uid, v in data['users'].items():
        for wd in v['workdays']:
            # todo: actually use a form here is better
            # todo: too much request to db

            dt = BaseConverter.parse_date(wd['dt'])
            try:
                wd_obj = WorkerDay.objects.get(worker_id=uid, dt=dt, child__id__isnull=True)
                if wd_obj.created_by or wd_obj.type != WorkerDay.Type.TYPE_EMPTY:
                    continue
            except WorkerDay.DoesNotExist:
                wd_obj = WorkerDay(
                    dt=BaseConverter.parse_date(wd['dt']),
                    worker_id=uid,
                )

            wd_obj.worker.shop_id = users[int(uid)].shop_id
            wd_obj.type = WorkerDayConverter.parse_type(wd['type'])
            if WorkerDay.is_type_with_tm_range(wd_obj.type):
                wd_obj.dttm_work_start = BaseConverter.parse_datetime(wd['dttm_work_start'])
                wd_obj.dttm_work_end = BaseConverter.parse_datetime(wd['dttm_work_end'])
                wd_obj.save()

                WorkerDayCashboxDetails.objects.filter(worker_day=wd_obj).delete()
                wdd_list = []

                for wdd in wd['details']:
                    wdd_el = WorkerDayCashboxDetails(
                        worker_day=wd_obj,
                        dttm_from=BaseConverter.parse_datetime(wdd['dttm_from']),
                        dttm_to=BaseConverter.parse_datetime(wdd['dttm_to']),
                    )
                    if wdd['type'] > 0:
                        wdd_el.work_type_id = wdd['type']
                    else:
                        wdd_el.status = WorkerDayCashboxDetails.TYPE_BREAK

                    wdd_list.append(wdd_el)
                WorkerDayCashboxDetails.objects.bulk_create(wdd_list)

            else:
                wd_obj.save()

    send_notification('C', timetable)

    return JsonResponse.success()
