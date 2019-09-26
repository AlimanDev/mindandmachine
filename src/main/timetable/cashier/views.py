from datetime import time, datetime, timedelta, date
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ObjectDoesNotExist
import json
from src.main.timetable.worker_exchange.utils import cancel_vacancies, create_vacancies_and_notify
from django.utils import timezone

from src.db.models import (
    User,
    Shop,
    WorkerDay,
    WorkerDayChangeRequest,
    ProductionDay,
    WorkerCashboxInfo,
    WorkerConstraint,
    WorkType,
    WorkerDayCashboxDetails,
    UserWeekdaySlot,
    WorkerDayApprove
)
from src.util.utils import (
    JsonResponse,
    api_method,
)
from src.util.forms import FormUtil
from src.util.models_converter import (
    UserConverter,
    WorkerDayConverter,
    WorkerConstraintConverter,
    WorkerCashboxInfoConverter,
    WorkTypeConverter,
    BaseConverter,
    WorkerDayChangeLogConverter,
)
from src.util.collection import group_by, count, range_u

from .forms import (
    GetCashierTimetableForm,
    SelectCashiersForm,
    GetCashierInfoForm,
    SetWorkerDayForm,
    SetWorkerRestrictionsForm,
    GetWorkerDayForm,
    CreateCashierForm,
    DeleteCashierForm,
    GetCashiersListForm,
    DublicateCashierTimetableForm,
    PasswordChangeForm,
    ChangeCashierInfo,
    GetWorkerDayChangeLogsForm,
    DeleteWorkerDayChangeLogsForm,
    GetWorkerChangeRequestsForm,
    HandleWorkerDayRequestForm,
)
from src.main.other.notification.utils import send_notification
from django.contrib.auth import update_session_auth_hash
from django.db import IntegrityError

import time as time_in_seconds

@api_method('GET', GetCashiersListForm)
def get_cashiers_list(request, form):
    """
    Возвращает список кассиров в данном магазине, уволенных позже чем dt_fired_after и нанятых\
    раньше, чем dt_hired_before.

    Args:
        method: GET
        url: /api/timetable/cashier/get_cashiers_list
        dt_hired_before(QOS_DATE): required = False.
        dt_fired_after(QOS_DATE): required False
        shop_id(int): required = True
        consider_outsource(bool): required = False (учитывать outsource работников)

    Returns:
        {[
            {
                | 'id': id пользователя,
                | 'username': username,
                | 'shop_id': id магазина к которому он привязан,
                | 'work_type': тип рабочего дня,
                | 'first_name': имя,
                | 'last_name': фамилия,
                | 'avatar_url': аватар,
                | 'dt_hired': дата найма,
                | 'dt_fired': дата увольнения,
                | 'auto_timetable': True/False,
                | 'comment': доп инфа,
                | 'sex': пол,
                | 'is_fixed_hours': True/False,
                | 'phone_number'(str): номер телефона,
                | 'is_ready_for_overworkings': True/False (готов сотрудник к переработкам или нет),
                | 'tabel_code': табельный номер,
            }, ...
        ]}

    """
    response_users = []
    attachment_groups = [User.GROUP_STAFF, User.GROUP_OUTSOURCE if form['consider_outsource'] else None]
    shop_id = form['shop_id']
    users_qs = User.objects.filter(
        shop_id=shop_id,
        attachment_group__in=attachment_groups
    ).order_by('id')

    if form['show_all']:
        response_users = users_qs
    else:
        for u in users_qs:
            if u.dt_hired is None or u.dt_hired <= form['dt_hired_before']:
                if u.dt_fired is None or u.dt_fired > form['dt_fired_after']:
                    response_users.append(u)

    return JsonResponse.success([UserConverter.convert(x) for x in response_users])


@api_method('GET', GetCashiersListForm)
def get_not_working_cashiers_list(request, form):
    """
    Возващает список пользователей, которые сегодня не работают

    Args:
        method: GET
        url: /api/timetable/cashier/get_not_working_cashiers_list
        dt_hired_before(QOS_DATE): required = False.
        dt_fired_after(QOS_DATE): required False
        shop_id(int): required = True

    Returns:
        {[
            {
                | 'id': id пользователя,
                | 'username': username,
                | 'shop_id': id магазина к которому он привязан,
                | 'work_type': тип рабочего дня,
                | 'first_name': имя,
                | 'last_name': фамилия,
                | 'avatar_url': аватар,
                | 'dt_hired': дата найма,
                | 'dt_fired': дата увольнения,
                | 'salary': зарплата,
                | 'auto_timetable': True/False,
                | 'comment': доп инфа,
                | 'sex': пол,
                | 'is_fixed_hours': True/False,
                | 'phone_number'(str): номер телефона,
                | 'is_ready_for_overworkings': True/False (готов сотрудник к переработкам или нет),
                | 'tabel_code': табельный номер,
            }, ...
        ]}
    """
    dt_now = datetime.now() + timedelta(hours=3)
    shop_id = form['shop_id']
    checkpoint = FormUtil.get_checkpoint(form)

    users_not_working_today = []

    for u in WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
            dt=dt_now.date(),
            worker__shop_id=shop_id,
            worker__attachment_group=User.GROUP_STAFF
    ).exclude(
        type=WorkerDay.Type.TYPE_WORKDAY.value
    ).order_by(
        'worker__last_name',
        'worker__first_name'
    ):
        if u.worker.dt_hired is None or u.worker.dt_hired <= form['dt_hired_before']:
            if u.worker.dt_fired is None or u.worker.dt_fired >= form['dt_fired_after']:
                users_not_working_today.append(u.worker)

    return JsonResponse.success([UserConverter.convert(x) for x in users_not_working_today])


@api_method('GET', SelectCashiersForm)
def select_cashiers(request, form):
    """
    Args:
        method: GET
        url: /api/timetable/cashier/select_cashiers
        work_types(list): required = True
        worker_ids(list): required = True
        workday_type(str): required = False
        workdays(str): required = False
        shop_id(int): required = True
        work_workdays(str): required = False
        from_tm(QOS_TIME): required = False
        to_tm(QOS_TIME): required = False
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    """
    shop_id = form['shop_id']
    checkpoint = FormUtil.get_checkpoint(form)

    users = User.objects.qos_filter_active(
        dt_from=date.today(),
        dt_to=date.today() + relativedelta(days=31),
        shop_id=shop_id,
        attachment_group=User.GROUP_STAFF,
    )

    cashboxes_type_ids = set(form.get('work_types', []))
    if len(cashboxes_type_ids) > 0:
        users_hits = set()
        for x in WorkerCashboxInfo.objects.select_related('work_type').filter(work_type__shop_id=shop_id, is_active=True):
            if x.work_type_id in cashboxes_type_ids:
                users_hits.add(x.worker_id)

        users = [x for x in users if x.id in users_hits]

    worker_ids = set(form.get('worker_ids', []))
    if len(worker_ids) > 0:
        users = [x for x in users if x.id in worker_ids]

    worker_days = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(worker__shop_id=shop_id)

    workday_type = form.get('workday_type')
    if workday_type is not None:
        worker_days = worker_days.filter(type=workday_type)

    workdays = form.get('workdays')
    if len(workdays) > 0:
        worker_days = worker_days.filter(dt__in=workdays)

    users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]

    work_workdays = form.get('work_workdays', [])
    if len(work_workdays) > 0:
        def __is_match_tm(__x, __tm_from, __tm_to):
            if __x.dttm_work_start.time() < __x.dttm_work_end.time():
                if __tm_from > __x.dttm_work_end.time():
                    return False
                if __tm_to < __x.dttm_work_start.time():
                    return False
                return True
            else:
                if __tm_from >= __x.dttm_work_start.time():
                    return True
                if __tm_to <= __x.dttm_work_end.time():
                    return True
                return False

        worker_days = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
            worker__shop_id=shop_id,
            type=WorkerDay.Type.TYPE_WORKDAY.value,
            dt__in=work_workdays
        )

        tm_from = form.get('from_tm')
        tm_to = form.get('to_tm')
        if tm_from is not None and tm_to is not None:
            worker_days = [x for x in worker_days if __is_match_tm(x, tm_from, tm_to)]

        users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]

    return JsonResponse.success([UserConverter.convert(x) for x in users])



@api_method('GET', GetCashierTimetableForm)
def get_cashier_timetable(request, form):
    """
    Возвращает информацию о расписании сотрудника

    Args:
        method: GET
        url: /api/timetable/cashier/get_cashier_timetable
        worker_ids(list): required = True
        from_dt(QOS_DATE): с какого числа смотреть расписание
        to_dt(QOS_DATE): по какое число
        shop_id(int): required = True
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            'user': { в формате как get_cashiers_list },\n
            'indicators': {
                | 'change_amount': количество измененных дней,
                | 'holiday_amount': количество выходных,
                | 'sick_day_amount': количество больничных,
                | 'vacation_day_amount': количество отпускных дней,
                | 'work_day_amount': количество рабочих дней,
                | 'work_day_in_holidays_amount': количество рабочих дней в выходные
            },\n
            'days': [
                {
                    'day': {
                        | 'id': id worker_day'a,
                        | 'dttm_added': дата добавления worker_day'a,
                        | 'dt': worker_day dt,
                        | 'worker': id пользователя,
                        | 'type': тип worker_day'a,
                        | 'dttm_work_start': дата-время начала работы,
                        | 'dttm_work_end': дата-время конца рабочего дня,
                        | 'work_types': [список id'шников типов касс, на которых сотрудник работает в этот день],
                    },\n
                    | 'change_requests': [список change_request'ов],
                }
            ]
        }

    """
    from_dt = form['from_dt']
    to_dt = form['to_dt']
    checkpoint = FormUtil.get_checkpoint(form)
    approved_only = form['approved_only']
    work_types = {w.id: w for w in WorkType.objects.select_related('shop').all()}

    response = {}
    # todo: rewrite with 1 request instead 80
    for worker_id in form['worker_ids']:
        worker_days_db = WorkerDay.objects.get_filter_version(
            checkpoint, approved_only
        ).select_related('worker').filter(
            worker_id=worker_id,
            worker__shop_id=form['shop_id'],
            dt__gte=from_dt,
            dt__lte=to_dt,
        ).order_by(
            'dt'
        ).values(
            'id',
            'type',
            'dttm_added',
            'dt',
            'worker_id',
            'dttm_work_start',
            'dttm_work_end',
            'work_types__id',
        )

        worker_days = []
        worker_days_mask = {}
        for wd in worker_days_db:
            if (wd['id'] in worker_days_mask) and wd['work_types__id']:
                ind = worker_days_mask[wd['id']]
                worker_days[ind].work_types_ids.append(wd['work_types__id'])
            else:
                worker_days_mask[wd['id']] = len(worker_days)
                wd_m = WorkerDay(
                    id=wd['id'],
                    type=wd['type'],
                    dttm_added=wd['dttm_added'],
                    dt=wd['dt'],
                    worker_id=wd['worker_id'],
                    dttm_work_start=wd['dttm_work_start'],
                    dttm_work_end=wd['dttm_work_end'],
                )
                if wd['work_types__id']:
                    wd_m.work_types_ids = [wd['work_types__id']]
                    work_type = work_types[wd_m.work_types_ids[0]]
                    if work_type.shop_id != form['shop_id']:
                        wd_m.other_shop = work_type.shop.title

                worker_days.append(
                    wd_m
                )

        official_holidays = [
            x.dt for x in ProductionDay.objects.filter(
                dt__gte=from_dt,
                dt__lte=to_dt,
                type=ProductionDay.TYPE_HOLIDAY,
            )
        ]

        wd_logs = WorkerDay.objects.select_related('worker').filter(
            worker_id=worker_id,
            dt__gte=from_dt,
            dt__lte=to_dt,
            parent_worker_day__isnull=False,
            worker__attachment_group=User.GROUP_STAFF
        )
        if approved_only:
            wd_logs = wd_logs.filter(
                worker_day_approve_id__isnull = False
            )
        worker_day_change_log = group_by(
            wd_logs,
            group_key=lambda _: WorkerDay.objects.qos_get_current_worker_day(_).id,
            sort_key=lambda _: _.id,
            sort_reverse=True
        )

        indicators_response = {
            'work_day_amount': count(worker_days, lambda x: x.type == WorkerDay.Type.TYPE_WORKDAY.value),
            'holiday_amount': count(worker_days, lambda x: x.type == WorkerDay.Type.TYPE_HOLIDAY.value),
            'sick_day_amount': count(worker_days, lambda x: x.type == WorkerDay.Type.TYPE_SICK.value),
            'vacation_day_amount': count(worker_days, lambda x: x.type == WorkerDay.Type.TYPE_VACATION.value),
            'work_day_in_holidays_amount': count(worker_days, lambda x: x.type == WorkerDay.Type.TYPE_WORKDAY.value and
                                                                        x.dt in official_holidays),
            'change_amount': len(worker_day_change_log)
        }

        days_response = []
        for obj in worker_days:
            days_response.append({
                'day': WorkerDayConverter.convert(obj),
                'change_log': [WorkerDayChangeLogConverter.convert(x) for x in
                               worker_day_change_log.get(obj.id, [])],
                'change_requests': []
                # 'change_requests': [WorkerDayChangeRequestConverter.convert(x) for x in
                #                     worker_day_change_requests.get(obj.id, [])[:10]]
            })

        user = User.objects.select_related('position').get(id=worker_id)

        response[worker_id] = {
            'indicators': indicators_response,
            'days': days_response,
            'user': UserConverter.convert(user)
        }
    return JsonResponse.success(response)


@api_method(
    'GET',
    GetCashierInfoForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id']).shop
)
def get_cashier_info(request, form):
    """
    Возвращает инфорацию о кассире в зависимости от опции info

    Args:
        method: GET
        url: /api/timetable/cashier/get_cashier_info
        worker_id(int): required = True
        info(str): general_info/work_type_info/constraints_info/work_hours

    Returns:
        {
            'general_info': {
                | 'id': id пользователя,
                | 'username': username,
                | 'shop_id': id магазина к которому он привязан,
                | 'work_type': тип рабочего дня,
                | 'first_name': имя,
                | 'last_name': фамилия,
                | 'avatar_url': аватар,
                | 'dt_hired': дата найма,
                | 'dt_fired': дата увольнения,
                | 'auto_timetable': True/False,
                | 'comment': доп инфа,
                | 'sex': пол,
                | 'is_fixed_hours': True/False,
                | 'phone_number'(str): номер телефона,
                | 'is_ready_for_overworkings': True/False (готов сотрудник к переработкам или нет),
                | 'tabel_code': табельный номер,
            },\n
            (список с пн-вс(0-6), с какого и по какое время может работать сотрудник)\n
            'work_hours': [
                {
                    | 'tm_from': с какого времени может работать
                    | 'tm_to': по какое
                },...
            ],\n
            'constraint_info': [
                список constraints по каким дням не может работать сотрудник
                {
                    | 'weekday': 0-6,
                    | 'worker': id сотрудника,
                    | 'id': id constaint'a,
                    | 'tm': время когда сотрудник не может работать
                }
            ],
            'work_type_info': {
                | 'work_type': [список типов касс в магазине],
                | 'worker_cashbox_info': [список касс за которыми может работать сотрудник]
            }

        }

    """
    response = {}

    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    if 'general_info' in form['info']:
        response['general_info'] = UserConverter.convert(worker)

    if 'work_type_info' in form['info']:
        worker_cashbox_info = WorkerCashboxInfo.objects.filter(worker_id=worker.id, is_active=True)
        work_types = WorkType.objects.filter(shop_id=worker.shop_id)
        response['work_type_info'] = {
            'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info],
            'work_type': {x.id: WorkTypeConverter.convert(x) for x in work_types}, # todo: delete this -- seems not needed
            'min_time_between_shifts': worker.min_time_btw_shifts,
            'shift_length_min': worker.shift_hours_length_min,
            'shift_length_max': worker.shift_hours_length_max,
            'norm_work_hours': worker.norm_work_hours,
            'week_availability': worker.week_availability,
        }

    if 'constraints_info' in form['info']:
        constraints = WorkerConstraint.objects.filter(worker_id=worker.id)
        response['constraints_info'] = [WorkerConstraintConverter.convert(x) for x in constraints]
        response['shop_times'] = {
            'tm_start': BaseConverter.convert_time(worker.shop.tm_shop_opens),
            'tm_end': BaseConverter.convert_time(worker.shop.tm_shop_closes)
        }

    if 'work_hours' in form['info']:
        def __create_time_obj(__from, __to):
            return {
                'from': BaseConverter.convert_time(__from.time()),
                'to': BaseConverter.convert_time(__to.time())
            }

        constraint_times_all = {i: set() for i in range(7)}
        for x in WorkerConstraint.objects.filter(worker_id=worker.id):
            constraint_times_all[x.weekday].add(x.tm)

        constraint_times_all = {k: set(v) for k, v in constraint_times_all.items()}
        work_hours_all = {}

        dttm_from = datetime(year=1971, month=1, day=1)
        dttm_to = dttm_from + timedelta(days=1)
        dttm_step = timedelta(minutes=30)
        for weekday, constraint_times in constraint_times_all.items():
            times = [dttm for dttm in range_u(dttm_from, dttm_to, dttm_step, False) if
                     dttm.time() not in constraint_times]
            work_hours = []

            if len(times) > 0:
                begin = times[0]
                for t1, t2 in zip(times, times[1:]):
                    if t2 - t1 != dttm_step:
                        work_hours.append(__create_time_obj(begin, t1 + dttm_step))
                        begin = t2
                work_hours.append(__create_time_obj(begin, times[-1] + dttm_step))

            work_hours_all[weekday] = work_hours

        response['work_hours'] = work_hours_all

    return JsonResponse.success(response)


@api_method(
    'GET',
    GetWorkerDayForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id']).shop
)
def get_worker_day(request, form):
    """
    Возвращает информацию по конкретному дню сотрудника

    Args:
        method: GET
        url: /api/timetable/cashier/get_worker_day
        worker_id(int): id пользователя
        dt(QOS_DATE): на какую дату хотим посмотреть worker_day
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            'details': [
                {
                    | 'tm_to': до какого времени объект WorkerDayCashboxDetails,
                    | 'tm_from': от какого времени,
                    | 'work_type': id типа кассы за которым работает сотрудник (либо null)
                }
            ],\n
            'work_types': [
                work_type_id: {
                    | 'id': id типа кассы
                    | 'dttm_added': дата добавления кассы,
                    | 'dttm_deleted': дата удаления,
                    | 'speed_coef': int,
                    | 'shop':	id магазина,
                    | 'name': имя типа
                ],..\n
            },\n
            'day': {
                | 'id': id worker_day'a,
                | 'tm_work_end': ,
                | 'worker': id worker'a,
                | 'work_types': [],
                | 'type': тип worker_day'a,
                | 'dttm_work_start': ,
                | 'dttm_work_end': ,
                | 'dttm_added': ,
                | 'dt': дата создания worker_day'a
            },\n
            видимо список рабочих часов сотрудника\n
            'work_hours': [
                {
                    | 'from': с какого времени,
                    | 'to': по какое
                }
            ]
        }


    Raises:
        JsonResponse.does_not_exists_error: если нет такого объекта WorkerDay'a удвовлетворяющего\
        заданной дате и worker_id
        JsonResponse.intrnal_error: во всех остальных случаях

    """
    worker_id = form['worker_id']
    dt = form['dt']
    checkpoint = FormUtil.get_checkpoint(form)

    try:
        wd = WorkerDay.objects.qos_filter_version(checkpoint).get(dt=dt, worker_id=worker_id)
    except WorkerDay.DoesNotExist:
        return JsonResponse.does_not_exists_error()
    except WorkerDay.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    dttm_from = datetime.combine(dt, time())
    dttm_to = datetime.combine(dt + timedelta(days=1), time())
    dttm_step = timedelta(minutes=30)

    constraint_times = set(x.tm for x in WorkerConstraint.objects.filter(worker_id=worker_id, weekday=dt.weekday()))
    times = [dttm for dttm in range_u(dttm_from, dttm_to, dttm_step, False) if dttm.time() not in constraint_times]
    work_hours = []

    def __create_time_obj(__from, __to):
        return {
            'from': BaseConverter.convert_time(__from.time()),
            'to': BaseConverter.convert_time(__to.time())
        }

    if len(times) > 0:
        begin = times[0]
        for t1, t2 in zip(times, times[1:]):
            if t2 - t1 != dttm_step:
                work_hours.append(__create_time_obj(begin, t1 + dttm_step))
                begin = t2
        work_hours.append(__create_time_obj(begin, times[-1] + dttm_step))

    details = []
    cashboxes_types = {}
    for x in WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint). \
            select_related('on_cashbox', 'work_type'). \
            filter(worker_day=wd):
        details.append({
            'dttm_from': BaseConverter.convert_time(x.dttm_from.time()) if x.dttm_to else None,
            'dttm_to': BaseConverter.convert_time(x.dttm_to.time()) if x.dttm_to else None,
            'work_type': x.work_type_id,
        })
        cashboxes_types[x.work_type_id] = WorkTypeConverter.convert(x.work_type)

    return JsonResponse.success({
        'day': WorkerDayConverter.convert(wd),
        'work_hours': work_hours,
        'details': details,
        'work_types': cashboxes_types
    })


# todo: refactor this function
@api_method(
    'POST',
    SetWorkerDayForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id']).shop
)
def set_worker_day(request, form):
    """
    Меняет конкретный рабочий день работяги

    Args:
        method: POST
        url: /api/timetable/cashier/set_worker_day
        worker_id(int): required = True
        dt(QOS_DAT): дата рабочего дня
        type(str): required = True. новый тип рабочего дня
        dttm_work_start(QOS_TIME): новое время начала рабочего дня
        dttm_work_end(QOS_TIME): новое время конца рабочего дня
        work_type(int): required = False. на какой специализации он будет работать
        comment(str): max_length=128, required = False
        details(srt): детали рабочего дня (заносятся в WorkerDayCashboxDetails)

    Returns:
        {
            'day': {
                | 'id': id нового WorkerDay'a,
                | 'dttm_added': сейчас,
                | 'dt': дата WorkerDay'a,
                | 'worker': id worker'a,
                | 'type': тип,
                | 'dttm_work_start': время начала рабочего дня,
                | 'dttm_work_end': время конца рабочего дня,
                | 'work_types'(list): специализации (id'шники типов касс)
            },\n
            'action': 'update'/'create',\n
            'cashbox_updated': True/False
        }
    Raises:
        JsonResponse.multiple_objects_returned
    """

    if form['details']:
        details = json.loads(form['details'])
    else:
        details = []
    dt = form['dt']
    response = {}

    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    wd_args = {
        'dt': dt,
        'type': form['type'],
    }

    if WorkerDay.is_type_with_tm_range(form['type']):
        dttm_work_start = datetime.combine(dt, form['tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
        tm_work_end = form['tm_work_end']
        dttm_work_end = datetime.combine(form['dt'], tm_work_end) if tm_work_end > form['tm_work_start'] else \
            datetime.combine(dt + timedelta(days=1), tm_work_end)
        wd_args.update({
            'dttm_work_start': dttm_work_start,
            'dttm_work_end': dttm_work_end,
        })

    else:
        wd_args.update({
            'dttm_work_start': None,
            'dttm_work_end': None,
        })

    try:
        old_wd = WorkerDay.objects.qos_current_version().get(
            worker_id=worker.id,
            dt=form['dt']
        )
        action = 'update'
    except WorkerDay.DoesNotExist:
        old_wd = None
        action = 'create'
    except WorkerDay.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    if old_wd:
        # old_wd_type = old_wd.type
        # Не пересохраняем, если тип не изменился
        if old_wd.type == form['type'] and not WorkerDay.is_type_with_tm_range(form['type']):
            return JsonResponse.success()

        # этот блок вводит логику относительно аутсорс сотрудников. у них выходных нет, поэтому их мы просто удаляем
        if old_wd.worker.attachment_group == User.GROUP_OUTSOURCE:
            try:
                WorkerDayCashboxDetails.objects.filter(worker_day=old_wd).delete()
            except ObjectDoesNotExist:
                pass
            old_wd.delete()
            old_wd = None


    # todo: fix temp code -- if status TYPE_EMPTY or TYPE_DELETED then delete all sequence of worker_day -- possible to recreate timetable
    if worker.attachment_group == User.GROUP_STAFF and form['type'] in \
        [WorkerDay.Type.TYPE_EMPTY.value, WorkerDay.Type.TYPE_DELETED.value]:
        while old_wd:
            WorkerDayCashboxDetails.objects.filter(worker_day=old_wd).delete()
            old_wd.delete()
            old_wd = old_wd.parent_worker_day if old_wd.parent_worker_day_id else None


    elif worker.attachment_group == User.GROUP_STAFF \
            or worker.attachment_group == User.GROUP_OUTSOURCE \
                    and form['type'] == WorkerDay.Type.TYPE_WORKDAY.value:
        new_worker_day = WorkerDay.objects.create(
            worker_id=worker.id,
            parent_worker_day=old_wd,
            created_by=request.user,
            **wd_args
        )
        if new_worker_day.type == WorkerDay.Type.TYPE_WORKDAY.value:
            if len(details):
                for item in details:
                    dttm_to = BaseConverter.parse_time(item['dttm_to'])
                    dttm_from = BaseConverter.parse_time(item['dttm_from'])
                    WorkerDayCashboxDetails.objects.create(
                        work_type_id=item['work_type'],
                        worker_day=new_worker_day,
                        dttm_from=datetime.combine(dt, dttm_from),
                        dttm_to=datetime.combine(dt, dttm_to) if dttm_to > dttm_from\
                            else datetime.combine(dt + timedelta(days=1), dttm_to)
                    )
            else:
                work_type_id = form.get('work_type')
                WorkerDayCashboxDetails.objects.create(
                    work_type_id=work_type_id,
                    worker_day=new_worker_day,
                    dttm_from=new_worker_day.dttm_work_start,
                    dttm_to=new_worker_day.dttm_work_end
                )

            response['day'] = WorkerDayConverter.convert(new_worker_day)

    elif worker.attachment_group == User.GROUP_OUTSOURCE:
        worker.delete()

    response = {
        'action': action
    }

    shop = Shop.objects.get(user=form['worker_id'])
    work_type_id = WorkType.objects.get(id=form['work_type']).id if form['work_type'] else None
    if work_type_id is None:
        work_type_id = WorkerDayCashboxDetails.objects.filter(
            worker_day=old_wd,
            dttm_deleted__isnull=True
        ).first()
        work_type_id = work_type_id.work_type_id if not work_type_id is None else None

    if (form['type'] == WorkerDay.Type.TYPE_WORKDAY.value) and work_type_id:
        cancel_vacancies(shop.id, work_type_id)
    if (form['type'] != WorkerDay.Type.TYPE_WORKDAY.value) and work_type_id:
        create_vacancies_and_notify(shop.id, work_type_id) # todo: fix this row

    return JsonResponse.success(response)


@api_method('GET', GetWorkerDayChangeLogsForm)
def get_worker_day_logs(request, form):
    """
    Получаем список изменений в расписании (либо конкретного сотрудника, если указыван worker_day_id), либо всех (иначе)

    Args:
        method: GET
        url: /api/timetable/cashier/get_worker_day_logs
        shop_id(int): required = True
        from_dt(QOS_DATE): required = True. от какой даты брать логи
        to_dt(QOS_DATE): required = True. до какой даты
        worker_day_id(int): required = False
        size(int): сколько записей отдавать (то есть отдаст срез [pointer: pointer + size]. required = False (default 10)

    Returns:
         {
            Список worker_day'ев (детей worker_day_id, либо все worker_day'и, у которых есть дети)
         }

    Raises:
        JsonResponse.does_not_exist_error: если рабочего дня с worker_day_id нет
    """

    def convert_change_log(obj):
        def __work_dttm(__field):
            return BaseConverter.convert_datetime(__field) if obj.type == WorkerDay.Type.TYPE_WORKDAY.value else None

        return {
            'id': obj.id,
            'dttm_added': BaseConverter.convert_datetime(obj.dttm_added),
            'dt': BaseConverter.convert_date(obj.dt),
            'worker': obj.worker_id,
            'type': WorkerDayConverter.convert_type(obj.type),
            'dttm_work_start': __work_dttm(obj.dttm_work_start),
            'dttm_work_end': __work_dttm(obj.dttm_work_end),
            'created_by': obj.created_by_id,
            'created_by_fio': obj.created_by.get_fio(),
            'prev_type': WorkerDayConverter.convert_type(obj.parent_worker_day.type),
            'prev_dttm_work_start': __work_dttm(obj.parent_worker_day.dttm_work_start),
            'prev_dttm_work_end': __work_dttm(obj.parent_worker_day.dttm_work_end),
        }

    shop_id = form['shop_id']
    worker_day_id = form['worker_day_id']

    worker_day_desired = None
    response_data = []

    if worker_day_id:
        try:
            worker_day_desired = WorkerDay.objects.get(id=worker_day_id)
        except WorkerDay.DoesNotExist:
            return JsonResponse.does_not_exists_error('Ошибка. Такого рабочего дня в расписании нет.')

    active_users = User.objects.qos_filter_active(
        dt_from=form['from_dt'],
        dt_to=form['to_dt'],
        shop_id=shop_id,
        attachment_group=User.GROUP_STAFF
    )

    child_worker_days = WorkerDay.objects.select_related('worker', 'parent_worker_day', 'created_by').filter(
        worker__in=active_users,
        parent_worker_day_id__isnull=False,
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt'],
    ).order_by('-dttm_added')
    if worker_day_desired:
        child_worker_days = child_worker_days.filter(
            dt=worker_day_desired.dt,
            worker_id=worker_day_desired.worker_id,
        )

    for child in child_worker_days:
        response_data.append(convert_change_log(child))

    return JsonResponse.success(response_data)


@api_method(
    'POST',
    DeleteWorkerDayChangeLogsForm,
    lambda_func=lambda x: WorkerDay.objects.get(id=x['worker_day_id']).worker.shop
)
def delete_worker_day(request, form):
    """
    Удаляет объект WorkerDay'a с worker_day_id из бд. При этом перезаписывает parent_worker_day

    Args:
        method: POST
        url: /api/timetable/cashier/delete_worker_day
        worker_day_id(int): required = True

    Raises:
        JsonResponse.does_not_exists_error: если такого рабочего дня нет в бд
        JsonResponse.internal_error: ошибка при удалении из базы, либо если пытаемся удалить версию, составленную расписанием
    """
    try:
        worker_day_to_delete = WorkerDay.objects.get(id=form['worker_day_id'])
    except WorkerDay.DoesNotExist:
        return JsonResponse.access_forbidden('Такого рабочего дня нет в расписании.')

    wd_parent = worker_day_to_delete.parent_worker_day

    if wd_parent is None:
        return JsonResponse.internal_error('Нельзя удалить версию, составленную расписанием.')

    try:
        wd_child = worker_day_to_delete.child
    except:
        wd_child = None

    if wd_child is not None:
        wd_child.parent_worker_day = wd_parent

    try:
        worker_day_to_delete.parent_worker_day = None
        worker_day_to_delete.save()

        if wd_child:
            wd_child.save()
        try:
            WorkerDayCashboxDetails.objects.get(worker_day_id=worker_day_to_delete.id).delete()
        except:
            pass
        worker_day_to_delete.delete()
    except:
        return JsonResponse.internal_error('Не удалось удалить день из расписания.')

    return JsonResponse.success()

#
# @api_method(
#     'POST',
#     SetCashierInfoForm,
#     lambda_func=lambda x: User.objects.get(id=x['worker_id'])
# )
# def set_cashier_info_hard(request, form):
#     """
#     url: /api/timetable/cashier/set_cashier_info_hard
#     """
#     return set_cashier_info(request, form, False)
#
#
# @api_method(
#     'POST',
#     SetCashierInfoForm,
#     lambda_func=lambda x: User.objects.get(id=x['worker_id'])
# )
# def set_cashier_info_lite(request, form):
#     """
#     url: /api/timetable/cashier/set_cashier_info_lite
#     """
#     return set_cashier_info(request, form, True)


@api_method(
    'POST',
    SetWorkerRestrictionsForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id']).shop
)
def set_worker_restrictions(request, form):
    """
    Устанавливает заданные параметры кассиру

    Args:
        method: POST
        url: /api/timetable/cashier/set_worker_restrictions
        worker_id(int): required = True
        # worker_sex(str): пол
        # work_type_info(str): JSON за какими типами работ может работать
        # constraints(str): JSON с ограничениями сотрудника
        # is_ready_for_overworkings(bool): готов ли сотрудник к переработкам
        # is_fixed_hours(bool): делать график фиксированным или нет
        worker_slots(str): JSON со слотами на которых сотрудник может (или нежелательно работать)
        # week_availability(int): сколько подряд может работать (например, если стоит 2, то считаем график 2через2)
        # norm_work_hours(int): отклонение от нормы рабочих часов для сотрудника
        # shift_hours_length(str): длина смен в часах в формате '5-12'
        # min_time_btw_shifts(int): минимальное время между сменами

    Returns:
        {}
    """

    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')


    # WorkTypes
    work_type_info = form.get('work_type_info', [])
    curr_work_types = {wci.work_type_id: wci for wci in WorkerCashboxInfo.objects.filter(worker=worker,)}
    for work_type in work_type_info:
        wci = curr_work_types.pop(work_type['work_type_id'], None)
        if wci:
            wci.priority = work_type['priority']
            wci.save()
        else:
            try:
                WorkerCashboxInfo.objects.create(
                    worker=worker,
                    work_type_id=work_type['work_type_id'],
                    priority=work_type['priority'],
                )
            except IntegrityError:
                pass

    del_old_wcis_ids = [wci.id for wci in curr_work_types.values()]
    WorkerCashboxInfo.objects.filter(id__in=del_old_wcis_ids).delete()

    if type(form.get('constraints')) == list:
        new_constraints = form['constraints']
        WorkerConstraint.objects.filter(worker=worker).delete()
        constraints_to_create = []

        for constraint in new_constraints:
            constraints_to_create.append(
                WorkerConstraint(
                    tm=BaseConverter.parse_time(constraint['tm']),
                    is_lite=constraint['is_lite'],
                    weekday=constraint['weekday'],
                    worker=worker
                )
            )
        WorkerConstraint.objects.bulk_create(constraints_to_create)

    if type(form.get('worker_slots')) == list:
        new_slots = form['worker_slots']
        UserWeekdaySlot.objects.filter(worker=worker).delete()

        slots_to_create = []
        for user_slot in new_slots:
            slots_to_create.append(
                UserWeekdaySlot(
                    worker=worker,
                    slot_id=user_slot['slot_id'],
                    is_suitable=user_slot['is_suitable'],
                    weekday=user_slot['weekday']
                )
            )
        UserWeekdaySlot.objects.bulk_create(slots_to_create)

    worker.sex = form['worker_sex']
    worker.week_availability = form['week_availability']
    worker.is_fixed_hours = form['is_fixed_hours']
    worker.shift_hours_length_min = form['shift_hours_length'][0]
    worker.shift_hours_length_max = form['shift_hours_length'][1]
    worker.is_ready_for_overworkings = form['is_ready_for_overworkings']
    worker.norm_work_hours = form['norm_work_hours']
    worker.min_time_btw_shifts = form['min_time_btw_shifts']

    worker.save()

    return JsonResponse.success()


@api_method('POST', CreateCashierForm)
def create_cashier(request, form):
    """
    Создает кассира

    Args:
        method: POST
        url: /api/timetable/cashier/create_cashier
        first_name(str): max_length = 30, required = True
        middle_name(str): max_length = 64, required = True
        last_name(str): max_length = 150, required = True
        username(str): max_length = 150, required = True
        password(str): max_length = 64, required = True
        dt_hired(QOS_DATE): дата найма, required = True
        shop_id(int): required = True

    Note:
        также отправляет уведомление о том, что пользователь был создан

    Returns:
        {
            | 'id': id user'a,
            | 'username': ,
            | 'shop_id': ,
            | 'first_name': ,
            | 'last_name': ,
            | 'avatar_url': ,
            | 'dt_hired': ,
            | 'dt_fired': ,
            | 'auto_timetable': ,
            | 'comment': ,
            | 'sex': ,
            | 'is_fixed_hours': ,
            | 'phone_number': ,
            | 'is_ready_for_overworkings': ,
            | 'tabel_code':
        }
    """
    username = str(time_in_seconds.time() * 1000000)[:-2]
    try:
        user = User.objects.create_user(username=username, password=form['password'])
        user.first_name = form['first_name']
        user.middle_name = form['middle_name']
        user.last_name = form['last_name']
        user.shop_id = form['shop_id']
        user.dt_hired = form['dt_hired']
        user.username = 'u' + str(user.id)
        user.save()
    except:
        return JsonResponse.already_exists_error()

    send_notification('C', user, sender=request.user)

    return JsonResponse.success(UserConverter.convert(user))


@api_method('POST', DublicateCashierTimetableForm)
def dublicate_cashier_table(request, form):
    """
    Здесь будем использовать только актуальные данные (qos_current_version)

    Note:
        пока не используется. функция для стажеров и наставников

    Args:
        method: POST
        url: /api/timetable/cashier/dublicate_cashier_table
        from_worker_id(int): required = True
        to_worker_id(int): required = True
        from_dt(QOS_DATE): дата начала копирования расписания
        to_dt(QOS_DATE): дата конца копирования
        shop_id(int): required = True
    """
    from_worker_id = form['from_worker_id']
    to_worker_id = form['to_worker_id']
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    main_worker_days = list(WorkerDay.objects.qos_current_version().filter(
        worker_id=from_worker_id,
        dt__gte=from_dt,
        dt__lte=to_dt
    ))
    main_worker_days_details = WorkerDayCashboxDetails.objects.qos_current_version().filter(
        worker_day__in=list(map(lambda x: x.id, main_worker_days)),
    )
    # todo: add several details, not last
    main_worker_days_details = {wdds.worker_day_id: wdds for wdds in main_worker_days_details}

    trainee_worker_days = WorkerDay.objects.qos_current_version().filter(
        worker_id=to_worker_id,
        dt__gte=from_dt,
        dt__lte=to_dt
    )
    WorkerDayCashboxDetails.objects.filter(worker_day__in=trainee_worker_days).delete()
    trainee_worker_days.delete()

    wdcds_list_to_create = []
    for blank_day in main_worker_days:
        new_wd = WorkerDay.objects.create(
            worker_id=to_worker_id,
            dt=blank_day.dt,
            type=blank_day.type,
            dttm_work_start=blank_day.dttm_work_start,
            dttm_work_end=blank_day.dttm_work_end,
        )
        new_wdcds = main_worker_days_details.get(blank_day.id)
        if new_wdcds:
            wdcds_list_to_create.append(
                WorkerDayCashboxDetails(
                    worker_day=new_wd,
                    on_cashbox=new_wdcds.on_cashbox,
                    work_type=new_wdcds.work_type,
                    dttm_from=new_wdcds.dttm_from,
                    dttm_to=new_wdcds.dttm_to
                )
            )

    WorkerDayCashboxDetails.objects.bulk_create(wdcds_list_to_create)
    return JsonResponse.success()


@api_method(
    'POST',
    DeleteCashierForm,
    lambda_func=lambda x: User.objects.get(id=x['user_id']).shop
)
def delete_cashier(request, form):
    """
    "Удаляет" кассира (на самом деле просто проставляет dt_fired)

    Args:
        method: POST
        url: /api/timetable/cashier/delete_cashier
        user_id(int): required = True
        dt_fired(QOS_DATE): дата увольнения. required = True

    Note:
        также отправляет уведомление о том, что пользователь был удален

    Returns:
        тот же дикт, что и create_cashier

    Raises:
        JsonResponse.does_not_exists_error: если такого пользователя нет

    """
    try:
        user = User.objects.get(id=form['user_id'])
    except User.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    user.dt_fired = form['dt_fired']
    user.set_unusable_password()
    user.save()

    send_notification('D', user, sender=request.user)

    return JsonResponse.success(UserConverter.convert(user))


@api_method(
    'POST',
    PasswordChangeForm,
    lambda_func=lambda x: User.objects.get(id=x['user_id']).shop
)
def password_edit(request, form):
    """
    Меняет пароль пользователя. Если группа пользователя S или D, он может менять пароль всем

    Args:
        method: POST
        url: /api/timetable/cashier/password_edit
        user_id(int): required = True
        old_password(str): max_length = 128, required = False
        new_password(str): max_length = 128, required = True

    Returns:
        дикт как в create_user
    """
    user_id = form['user_id']
    old_password = form['old_password']
    new_password = form['new_password']

    if user_id != request.user.id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse.does_not_exists_error()
    else:
        user = request.user

    if not request.user.check_password(old_password):
        return JsonResponse.access_forbidden()

    user.set_password(new_password)
    update_session_auth_hash(request, user)
    user.save()

    return JsonResponse.success(UserConverter.convert(user))


@api_method(
    'GET',
    GetWorkerChangeRequestsForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id']).shop
)
def get_change_request(request, form):
    """

    Args:
        method: GET
        api: /api/timetable/cashier/get_change_request
        dt(QOS_DATE): change request'ы на эту дату
        worker_id: для какого работника

    Returns:
         {
            dt:
            type: тип рабочего дня
            dttm_work_start:
            dttm_work_end:
            wish_text: текст пожелания
            is_approved: одобрен ли реквест или нет
         }
    Raises:
        JsonResponse.internal_error: если в бд лежит несколько запросов на этот день (по идее такого не должно быть)

    """
    try:
        change_request = WorkerDayChangeRequest.objects.get(dt=form['dt'], worker_id=form['worker_id'])
        return JsonResponse.success({
            'dt': BaseConverter.convert_date(change_request.dt),
            'type': WorkerDayConverter.convert_type(change_request.type),
            'dttm_work_start': BaseConverter.convert_datetime(change_request.dttm_work_start),
            'dttm_work_end': BaseConverter.convert_datetime(change_request.dttm_work_end),
            'wish_text': change_request.wish_text,
            'status_type': change_request.status_type,
        })
    except WorkerDayChangeRequest.DoesNotExist:
        return JsonResponse.success()
    except WorkerDayChangeRequest.MultipleObjectsReturned:
        return JsonResponse.internal_error('Существует несколько запросов на этот день. Не знаю какой выбрать.')

# views for making requests for changing worker day from mobile application


@api_method(
    'POST',
    ChangeCashierInfo,
    lambda_func=lambda x: User.objects.get(id=x['user_id']).shop,
    check_password=True,
)
def change_cashier_info(request, form):
    """

    Args:
        method: POST
        api: /api/timetable/cashier/change_cashier_info
        user_id(int): required = True
        first_name(str): required = False
        middle_name(str): required = False
        last_name(str): required = False
        phone_number(str): required = False
        email(str): required = False
        dt_hired(QOS_DATE): required = False
        dt_fired(QOS_DATE): required = False
        group(str): required = False. Группа пользователя ('C'/'S'/'M'/'D'/'H')

    Returns:
         сложный дикт
    """
    user_id = form['user_id']

    if user_id != request.user.id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse.does_not_exists_error()
    else:
        user = request.user

    if form['first_name']:
        user.first_name = form['first_name']
    if form['middle_name']:
        user.middle_name = form['middle_name']
    if form['last_name']:
        user.last_name = form['last_name']
    if form['tabel_code']:
        user.tabel_code = form['tabel_code']
    if form['salary']:
        user.salary = form['salary']
    if form['phone_number']:
        user.phone_number = form['phone_number']
    if form['email']:
        user.email = form['email']
    if form['dt_hired']:
        user.dt_hired = form['dt_hired']
    if form['dt_fired']:
        user.dt_fired = form['dt_fired']

        WorkerDayCashboxDetails.objects.filter(
            worker_day__worker=user,
            worker_day__dt__gte=form['dt_fired'],
            is_vacancy=False,
        ).delete()

        WorkerDayCashboxDetails.objects.filter(
            worker_day__worker=user,
            worker_day__dt__gte=form['dt_fired'],
            is_vacancy=True,
        ).update(
            dttm_deleted=timezone.now(),
            status=WorkerDayCashboxDetails.TYPE_DELETED,
        )

    user.save()

    return JsonResponse.success()


# todo: drop not used method (check mobile)
# запрос на изменение рабочего дня возможно с мобильного устройства приходит)
@api_method(
    'POST',
    SetWorkerDayForm,
    # check_permissions=False,
)
def request_worker_day(request, form):
    """

        Args:
            method: POST
            api: /api/timetable/cashier/request_worker_day
            worker_id(int): ид работника
            dt(QOS_DATE): дата на которую делается request
            type(char): тип рабочего дня который хочет работник
            tm_work_start(QOS_TIME):
            tm_work_end(QOS_TIME):
            wish_text(char): текст пожелания который потом уйдет в уведомлении

        Returns:
             {}
        Raises:
            JsonResponse.internal_error: если не получилось создать запрос на этот день (скорее всего ошибка в send_notificitation методе)
        """
    dt = form['dt']
    tm_work_start = form['tm_work_start']
    tm_work_end = form['tm_work_end']
    worker_id = form['worker_id']

    existing_requests = WorkerDayChangeRequest.objects.filter(dt=dt, worker_id=worker_id)
    # Notifications.objects.filter(object_id__in=existing_requests.values_list('id')).delete()
    existing_requests.delete()

    if tm_work_end and tm_work_start:
        dttm_work_start = datetime.combine(dt, tm_work_start)
        dttm_work_end = datetime.combine(dt, tm_work_end) if tm_work_end > tm_work_start\
            else datetime.combine(dt + timedelta(days=1), tm_work_end)
    else:
        dttm_work_start = dttm_work_end = None
    try:
        change_request = WorkerDayChangeRequest.objects.create(
            worker_id=worker_id,
            dt=dt,
            type=form['type'],
            dttm_work_start=dttm_work_start,
            dttm_work_end=dttm_work_end,
            wish_text=form['wish_text']
        )

        send_notification('C', change_request, sender=request.user)
    except Exception as exc:
        print(exc)
        return JsonResponse.internal_error('Ошибка при создании запроса на изменение.')

    return JsonResponse.success()


@api_method(
    'POST',
    HandleWorkerDayRequestForm,
    lambda_func=lambda x: WorkerDayChangeRequest.objects.get(id=x['request_id']).worker.shop
)
def handle_worker_day_request(request, form):
    """
    Args:
        method: POST
        api: /api/timetable/cashier/handle_change_request
        request_id(int): id request'a
        action(char): 'A' for accept, 'D' for decline

    Returns:
         {}
    """
    request_id = form['request_id']
    action = form['action']

    try:
        change_request = WorkerDayChangeRequest.objects.get(id=request_id)
    except WorkerDayChangeRequest.DoesNotExist:
        return JsonResponse.does_not_exists_error('Такого запроса не существует.')

    new_notification_text = 'Ваш запрос на изменение рабочего дня на {} был '.format(change_request.dt)

    if action == 'A':
        try:
            old_wd = WorkerDay.objects.qos_current_version().get(
                dt=change_request.dt,
                worker_id=change_request.worker_id
            )
        except WorkerDay.DoesNotExist:
            old_wd = None

        WorkerDay.objects.create(
            worker_id=change_request.worker_id,
            dt=change_request.dt,
            type=change_request.type,
            dttm_work_start=change_request.dttm_work_start,
            dttm_work_end=change_request.dttm_work_end,
            created_by=request.user,
            parent_worker_day=old_wd
        )

        # Notifications.objects.create(
        #     to_worker_id=change_request.worker_id,
        #     type=Notifications.TYPE_INFO,
        #     text=new_notification_text+'одобрен.'
        # )
        change_request.status_type = WorkerDayChangeRequest.TYPE_APPROVED

    elif action == 'D':
        # Notifications.objects.create(
        #     to_worker_id=change_request.worker_id,
        #     type=Notifications.TYPE_INFO,
        #     text=new_notification_text + 'отклонен.'
        # )
        change_request.status_type = WorkerDayChangeRequest.TYPE_DECLINED
    else:
        return JsonResponse.internal_error('Неизвестное дейсвтие')

    change_request.save()
    # Notifications.objects.filter(object_id=change_request.id).delete()

    return JsonResponse.success()
