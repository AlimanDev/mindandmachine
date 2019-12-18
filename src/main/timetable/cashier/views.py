import json
import time as time_in_seconds
from datetime import time, datetime, timedelta, date

from dateutil.relativedelta import relativedelta

from django.contrib.auth import update_session_auth_hash
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError
from django.db.models import Q, F, Exists
from django.utils import timezone

from src.main.urv.utils import wd_stat_count_total
from src.db.models import (
    Employment,
    User,
    WorkerDay,
    WorkerDayChangeRequest,
    ProductionDay,
    WorkerCashboxInfo,
    WorkerConstraint,
    WorkerDayCashboxDetails,
    WorkerPosition,
    WorkType,
    UserWeekdaySlot,
    Shop,
)

from src.main.other.notification.utils import send_notification
from src.main.timetable.worker_exchange.utils import cancel_vacancies, create_vacancies_and_notify
from src.util.forms import FormUtil
from src.util.models_converter import (
    EmploymentConverter,
    UserConverter,
    WorkerDayConverter,
    BaseConverter,
    WorkerDayChangeLogConverter,
    Converter,
)
from src.util.utils import (
    JsonResponse,
    api_method,
)
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


@api_method('GET', GetCashiersListForm)
def get_cashiers_list(request, form):
    """
    Возвращает список кассиров в данном магазине

    Уволенных позже чем dt_from и нанятых раньше, чем dt_to.

    Args:
        method: GET
        url: /api/timetable/cashier/get_cashiers_list
        dt_from(QOS_DATE): required = False.
        dt_to(QOS_DATE): required False
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
    shop_id = form['shop_id']

    q = Q()
    if not form['show_all']:
        q &= Q(dt_hired__isnull=True) | Q(dt_hired__lte=form['dt_to'])
        q &= Q(dt_fired__isnull=True) | Q(dt_fired__gt=form['dt_from'])

    employments = list(Employment.objects.filter(
        shop_id=shop_id,
    ).filter(q).select_related('user').order_by('id'))

    return JsonResponse.success([EmploymentConverter.convert(x) for x in employments])


@api_method('GET', GetCashiersListForm)
def get_not_working_cashiers_list(request, form):
    """
    Возващает список пользователей, которые сегодня не работают

    Args:
        method: GET
        url: /api/timetable/cashier/get_not_working_cashiers_list
        dt_from(QOS_DATE): required = False.
        dt_to(QOS_DATE): required False
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

    users_not_working_today = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
            dt=dt_now.date(),
            employment__shop_id=shop_id,
    ).filter(
        (Q(employment__dt_hired__isnull=True) | Q(employment__dt_hired__lte=form['dt_to'])) &
        (Q(employment__dt_fired__isnull=True) | Q(employment__dt_fired__gt=form['dt_from']))
    ).exclude(
        type=WorkerDay.TYPE_WORKDAY
    ).order_by(
        'worker__last_name',
        'worker__first_name'
    )

    return JsonResponse.success([UserConverter.convert(x.worker) for x in users_not_working_today])


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

    employments = Employment.objects.get_active(
        dt_from=date.today(),
        dt_to=date.today() + relativedelta(days=31),
        shop_id=shop_id,
    )

    worker_ids = set(form.get('worker_ids', []))
    if len(worker_ids) > 0:
        employments = employments.filter(
            user_id__in=worker_ids
        )

    work_types = set(form.get('work_types', []))
    if len(work_types) > 0:
        employments_ids = WorkerCashboxInfo.objects.select_related('work_type').filter(
            work_type__shop_id=shop_id,
            is_active=True,
            work_type_id__in=work_types
        ).values_list('employment_id', flat=True)

        employments = employments.filter(id__in=employments_ids)



    worker_days = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(shop_id=shop_id)

    workday_type = form.get('workday_type')
    if workday_type is not None:
        worker_days = worker_days.filter(type=workday_type)

    workdays = form.get('workdays')
    if len(workdays) > 0:
        worker_days = worker_days.filter(dt__in=workdays)
        employments = employments.annotate(wd=Exists(worker_days)).filter(wd=True)
    # print (employments)

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
            shop_id=shop_id,
            type=WorkerDay.TYPE_WORKDAY,
            dt__in=work_workdays
        )

        tm_from = form.get('from_tm')
        tm_to = form.get('to_tm')
        if tm_from is not None and tm_to is not None:
            worker_days = [x for x in worker_days if __is_match_tm(x, tm_from, tm_to)]

        employments = [x for x in employments if x.user_id in set(y.worker_id for y in worker_days)]

    return JsonResponse.success([EmploymentConverter.convert(x) for x in employments])


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
        approved_only: required = False, только подтвержденные
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
    shop = Shop.objects.get(id=form['shop_id'])
    from_dt = form['from_dt']
    to_dt = form['to_dt']
    checkpoint = FormUtil.get_checkpoint(form)
    approved_only = form['approved_only']
    work_types = {w.id: w for w in WorkType.objects.select_related('shop').all()}
    def check_wd(wd):
            work_type=wd.work_types.first()
            if work_type and work_type.shop_id != form['shop_id']:
                wd.other_shop = work_type.shop.title
            return wd
    response = {}
    # todo: rewrite with 1 request instead 80
    for worker_id in form['worker_ids']:
        try:
            employment = Employment.objects.get(user_id=worker_id,shop_id=form['shop_id'])
        except ObjectDoesNotExist:
            continue

        worker_days_filter = WorkerDay.objects.qos_filter_version(checkpoint).select_related('employment').prefetch_related('work_types').filter(
            Q(employment__dt_fired__gt=from_dt) &
            Q(dt__lt=F('employment__dt_fired')) |
            Q(employment__dt_fired__isnull=True),

            Q(employment__dt_hired__lte=to_dt) &
            Q(dt__gte=F('employment__dt_hired')) |
            Q(employment__dt_hired__isnull=True),

            employment__user_id=worker_id,
            employment__shop_id=form['shop_id'],
            dt__gte=from_dt,
            dt__lte=to_dt,
        ).order_by(
            'dt'
        )
        worker_days = list(worker_days_filter)

        official_holidays = [
            x.dt for x in ProductionDay.objects.filter(
                dt__gte=from_dt,
                dt__lte=to_dt,
                type=ProductionDay.TYPE_HOLIDAY,
                region_id=shop.region_id,
            )
        ]

        wd_logs = WorkerDay.objects.select_related('employment').filter(
            Q(created_by__isnull=False),
            # Q(parent_worker_day__isnull=False) | Q(created_by__isnull=False),
            worker_id=worker_id,
            dt__gte=from_dt,
            dt__lte=to_dt,
        )

        if approved_only:
            wd_logs = wd_logs.filter(
                worker_day_approve_id__isnull=False
            )
        worker_day_change_log = {}
        for wd_log in list(wd_logs.order_by('-id')):
            key = WorkerDay.objects.qos_get_current_worker_day(wd_log).id
            if key not in worker_day_change_log:
                worker_day_change_log[key] = []
            worker_day_change_log[key].append(wd_log)
        '''

        wd_logs = list(wd_logs)
        worker_day_change_log = group_by(
            wd_logs,
            group_key=lambda _: WorkerDay.objects.qos_get_current_worker_day(_).id,
            sort_key=lambda _: _.id,
            sort_reverse=True
        )
        '''
        indicators_response = {}
        if (len(form['worker_ids']) == 1):
            indicators_response = {
                'work_day_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_WORKDAY),
                'holiday_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_HOLIDAY),
                'sick_day_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_SICK),
                'vacation_day_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_VACATION),
                'work_day_in_holidays_amount': sum(1 for x in worker_days if x.type == WorkerDay.TYPE_WORKDAY and
                                                                            x.dt in official_holidays),
                'change_amount': len(worker_day_change_log),
                'hours_count_fact': wd_stat_count_total(worker_days_filter, request.shop)['hours_count_fact']
            }
        worker_days = list(map(check_wd, worker_days))
        days_response = [
            {
                'day': WorkerDayConverter.convert(wd),
                'change_log': [WorkerDayChangeLogConverter.convert(x) for x in
                               worker_day_change_log.get(wd.id, [])],
                'change_requests': [],
            }
            for wd in worker_days
        ]

        response[worker_id] = {
            'indicators': indicators_response,
            'days': days_response,
            'user': EmploymentConverter.convert(employment)
        }
    return JsonResponse.success(response)


@api_method(
    'GET',
    GetCashierInfoForm,
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
        employment = Employment.objects.get(
            user_id=form['worker_id'],
            shop_id=form['shop_id'],
        )
        worker = User.objects.get(id=form['worker_id'])
    except Employment.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    if 'general_info' in form['info']:
        response['general_info'] = EmploymentConverter.convert(employment)

    if 'work_type_info' in form['info']:
        worker_cashbox_info = WorkerCashboxInfo.objects.filter(employment=employment, is_active=True)
        work_types = WorkType.objects.filter(shop_id=form['shop_id'])
        response['work_type_info'] = {
            'worker_cashbox_info': Converter.convert(
                worker_cashbox_info, 
                WorkerCashboxInfo, 
                fields=['id', 'employment__user_id', 'work_type_id', 'mean_speed', 'bills_amount', 'priority', 'duration']
            ),
            'work_type': {
                x['id']: x for x in Converter.convert(
                    work_types, 
                    WorkType, 
                    fields=['id', 'dttm_added', 'dttm_deleted', 'shop_id', 'priority', 'name', 'probability', 'prior_weight', 'min_workers_amount', 'max_workers_amount'],
                )
            }, # todo: delete this -- seems not needed
            'min_time_between_shifts': employment.min_time_btw_shifts,
            'shift_length_min': employment.shift_hours_length_min,
            'shift_length_max': employment.shift_hours_length_max,
            'norm_work_hours': employment.norm_work_hours,
            'week_availability': employment.week_availability,
            'dt_new_week_availability_from': BaseConverter.convert_date(employment.dt_new_week_availability_from),
        }

    if 'constraints_info' in form['info']:
        constraints = WorkerConstraint.objects.filter(worker_id=worker.id)
        response['constraints_info'] = Converter.convert(
            constraints, 
            WorkerConstraint, 
            fields=['id', 'worker_id', 'eployment__week_availability', 'weekday', 'tm', 'is_lite'],
        )
        response['shop_times'] = {
            'tm_start': BaseConverter.convert_time(request.shop.tm_shop_opens),
            'tm_end': BaseConverter.convert_time(request.shop.tm_shop_closes)
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
            times = [datetime.fromtimestamp(dttm) for dttm in range(int(dttm_from.timestamp()), int(dttm_to.timestamp()), int(dttm_step.total_seconds())) if
                     datetime.fromtimestamp(dttm).time() not in constraint_times]
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
    shop_id = form['shop_id']

    try:
        Employment.objects.get(
            user_id=worker_id,
            shop_id=shop_id,
        )
    except Employment.DoesNotExist:
        return JsonResponse.access_forbidden()

    dt = form['dt']
    checkpoint = FormUtil.get_checkpoint(form)

    try:
        wd = WorkerDay.objects.qos_filter_version(checkpoint).get(
            dt=dt,
            worker_id=worker_id,
            shop=request.shop)
    except WorkerDay.DoesNotExist:
        return JsonResponse.does_not_exists_error()
    except WorkerDay.MultipleObjectsReturned:
        return JsonResponse.multiple_objects_returned()

    dttm_from = datetime.combine(dt, time())
    dttm_to = datetime.combine(dt + timedelta(days=1), time())
    dttm_step = timedelta(minutes=30)

    constraint_times = set(x.tm for x in WorkerConstraint.objects.filter(worker_id=worker_id, weekday=dt.weekday()))
    times = [datetime.fromtimestamp(dttm) for dttm in range(int(dttm_from.timestamp()), \
        int(dttm_to.timestamp()), int(dttm_step.total_seconds())) if datetime.fromtimestamp(dttm).time() not in constraint_times]
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
        cashboxes_types[x.work_type_id] = Converter.convert(
            x.work_type, 
            WorkType, 
            fields=['id', 'dttm_added', 'dttm_deleted', 'shop_id', 'priority', 'name', 'probability', 'prior_weight', 'min_workers_amount', 'max_workers_amount'],
        )

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
)
def set_worker_day(request, form):
    """
    Меняет конкретный рабочий день работяги

    Args:
        method: POST
        url: /api/timetable/cashier/set_worker_day
        worker_id(int): required = True
        dt(QOS_DATE): дата рабочего дня / дата с которой менять
        dt_to(QOS_DATE): required = False / дата до которой менять
        type(str): required = True. новый тип рабочего дня
        tm_work_start(QOS_TIME): новое время начала рабочего дня
        tm_work_end(QOS_TIME): новое время конца рабочего дня
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

    details = []
    if form['details']:
        details = json.loads(form['details'])

    dt_from = form['dt']
    dt_to = form['dt_to']
    if (not dt_to):
        dt_to = dt_from

    is_type_with_tm_range = WorkerDay.is_type_with_tm_range(form['type'])

    response = []
    old_wds = []

    worker = User.objects.get(id=form['worker_id'])
    shop = request.shop
    employment = Employment.objects.get(
        user=worker,
        shop=shop)


    work_type = WorkType.objects.get(id=form['work_type']) if form['work_type'] else None

    for dt in range(int(dt_from.toordinal()), int(dt_to.toordinal()) + 1, 1):
        dt = date.fromordinal(dt)
        try:
            old_wd = WorkerDay.objects.qos_current_version().get(
                worker_id=worker.id,
                dt=dt,
                shop=shop
            )
            action = 'update'
        except WorkerDay.DoesNotExist:
            old_wd = None
            action = 'create'
        except WorkerDay.MultipleObjectsReturned:
            if (not form['dt_to']):
                return JsonResponse.multiple_objects_returned()
            response.append({
                'action': 'MultypleObjectsReturnedError',
                'dt': dt,
            })
            continue

        if old_wd:
            # Не пересохраняем, если тип не изменился
            if old_wd.type == form['type'] and not is_type_with_tm_range:
                if (not form['dt_to']):
                    return JsonResponse.success()
                response.append({
                    'action': 'TypeNotChanged',
                    'dt': dt
                })
                continue

        res = {
            'action': action
        }


        wd_args = {
            'dt': dt,
            'type': form['type'],
            'worker_id': worker.id,
            'shop': shop,
            'employment': employment,
            'parent_worker_day': old_wd,
            'created_by': request.user,
            'comment': form['comment'],
        }

        if is_type_with_tm_range:
            dttm_work_start = datetime.combine(dt, form[
                'tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
            tm_work_end = form['tm_work_end']
            dttm_work_end = datetime.combine(dt, tm_work_end) if tm_work_end > form['tm_work_start'] else \
                datetime.combine(dt + timedelta(days=1), tm_work_end)
            break_triplets = json.loads(shop.break_triplets)
            work_hours = WorkerDay.count_work_hours(break_triplets, dttm_work_start, dttm_work_end)
            wd_args.update({
                'dttm_work_start': dttm_work_start,
                'dttm_work_end': dttm_work_end,
                'work_hours': work_hours,
            })

        new_worker_day = WorkerDay.objects.create(
            **wd_args
        )
        if new_worker_day.type == WorkerDay.TYPE_WORKDAY:
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
                WorkerDayCashboxDetails.objects.create(
                    work_type=work_type,
                    worker_day=new_worker_day,
                    dttm_from=new_worker_day.dttm_work_start,
                    dttm_to=new_worker_day.dttm_work_end
                )


        res['day'] = WorkerDayConverter.convert(new_worker_day)

        response.append(res)
        if old_wd:
            old_wds.append(old_wd)

    old_cashboxdetails = WorkerDayCashboxDetails.objects.filter(
        worker_day__in=old_wds,
        dttm_deleted__isnull=True
    ).first()

    if work_type and form['type'] == WorkerDay.TYPE_WORKDAY:
        cancel_vacancies(work_type.shop_id, work_type.id)
    if old_cashboxdetails:
        create_vacancies_and_notify(old_cashboxdetails.work_type.shop_id, old_cashboxdetails.work_type_id)

    if (not form['dt_to']):
        response = response[0]

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
            return BaseConverter.convert_datetime(__field) if obj.type == WorkerDay.TYPE_WORKDAY else None

        res = {
            'id': obj.id,
            'dttm_added': BaseConverter.convert_datetime(obj.dttm_added),
            'dt': BaseConverter.convert_date(obj.dt),
            'worker': obj.worker_id,
            'type': obj.type,
            'dttm_work_start': __work_dttm(obj.dttm_work_start),
            'dttm_work_end': __work_dttm(obj.dttm_work_end),
            'created_by': obj.created_by_id,
            'comment': obj.comment,
            'created_by_fio': obj.created_by.get_fio() if obj.created_by else '',
        }
        if obj.parent_worker_day:
            res['prev_type'] = obj.parent_worker_day.type
            res['prev_dttm_work_start'] = __work_dttm(obj.parent_worker_day.dttm_work_start)
            res['prev_dttm_work_end']  = __work_dttm(obj.parent_worker_day.dttm_work_end)
        return res

    shop_id = form['shop_id']
    worker_day_id = form['worker_day_id']

    worker_day_desired = None
    response_data = []

    if worker_day_id:
        try:
            worker_day_desired = WorkerDay.objects.get(id=worker_day_id)
        except WorkerDay.DoesNotExist:
            return JsonResponse.does_not_exists_error('Ошибка. Такого рабочего дня в расписании нет.')

    user_ids = Employment.objects.get_active(
        dt_from=form['from_dt'],
        dt_to=form['to_dt'],
        shop_id=shop_id,
    ).values_list('user_id', flat=True)

    child_worker_days = WorkerDay.objects.select_related('worker', 'parent_worker_day', 'created_by').filter(
        Q(parent_worker_day__isnull=False) | Q(created_by__isnull=False),
        worker_id__in=user_ids,
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
    lambda_func=lambda x: WorkerDay.objects.get(id=x['worker_day_id']).shop
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

    wd_child = getattr(worker_day_to_delete, 'child', None)

    if wd_child is not None:
        wd_child.parent_worker_day = wd_parent

    try:
        worker_day_to_delete.parent_worker_day = None
        worker_day_to_delete.save()

        if wd_child:
            wd_child.save()
        WorkerDayCashboxDetails.objects.filter(worker_day_id=worker_day_to_delete.id).delete()
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
        # dt_new_week_availability_from(QOS_date): дата с которой нужно строить новый период

    Returns:
        {}
    """
    shop=request.shop

    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')
    
    try:
        employment = Employment.objects.get(
            user_id=worker.id,
            shop=shop,
        )
    except Employment.DoesNotExist:
        return JsonResponse.access_forbidden()

    # WorkTypes
    work_type_info = form.get('work_type_info', [])
    curr_work_types = {wci.work_type_id: wci for wci in WorkerCashboxInfo.objects.filter(employment=employment,)}
    
    for work_type in work_type_info:
        wci = curr_work_types.pop(work_type['work_type_id'], None)
        
        if wci:
            wci.priority = work_type['priority']
            wci.save()
        else:
            try:
                WorkerCashboxInfo.objects.create(
                    employment=employment,
                    work_type_id=work_type['work_type_id'],
                    priority=work_type['priority'],
                )
            except IntegrityError:
                pass
    
    del_old_wcis_ids = [wci.id for wci in curr_work_types.values()]
    WorkerCashboxInfo.objects.filter(id__in=del_old_wcis_ids).delete()
    
    if type(form.get('constraints')) == list:
        new_constraints = form['constraints']
        WorkerConstraint.objects.filter(employment=employment).delete()
        constraints_to_create = []

        for constraint in new_constraints:
            constraints_to_create.append(
                WorkerConstraint(
                    tm=BaseConverter.parse_time(constraint['tm']),
                    is_lite=constraint['is_lite'],
                    weekday=constraint['weekday'],
                    worker=worker,
                    employment=employment,
                    shop=shop
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
    
    worker.sex = form.get('worker_sex', 'M')
    worker.save()

    employment.week_availability = form.get('week_availability', 7)
    employment.is_fixed_hours = form.get('is_fixed_hours', False)
    employment.shift_hours_length_min = form['shift_hours_length'][0]
    employment.shift_hours_length_max = form['shift_hours_length'][1]
    employment.is_ready_for_overworkings = form.get('is_ready_for_overworkings', False)
    employment.norm_work_hours = form.get('norm_work_hours', 100)
    employment.min_time_btw_shifts = form.get('min_time_btw_shifts')
    employment.dt_new_week_availability_from = form.get('dt_new_week_availability_from')
    employment.save()

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
        user = User.objects.create_user(
            username=username,
            password=form['password'],
            first_name = form['first_name'],
            middle_name = form['middle_name'],
            last_name = form['last_name'],
        )
        user.username = 'u' + str(user.id)
        user.save()
        employment = Employment.objects.create(
            user_id = user.id,
            shop_id = form['shop_id'],
            dt_hired = form['dt_hired'],
        )
    except:
        return JsonResponse.already_exists_error()

    send_notification('C', user, sender=request.user)

    return JsonResponse.success(EmploymentConverter.convert(employment))


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
            shop_id=blank_day.shop_id,
            work_hours=blank_day.work_hours,
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
    lambda_func=lambda x: Employment.objects.get(user_id=x['user_id'], shop_id=x['shop_id']).shop
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
    employment = Employment.objects.get(
        user_id=form['user_id'],
        shop=form['shop_id'],
    )

    try:
        user = User.objects.get(id=form['user_id'])
    except User.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    employment.dt_fired = form['dt_fired']
    employment.save()

    send_notification('D', user, sender=request.user)

    return JsonResponse.success(UserConverter.convert(user))


@api_method(
    'POST',
    PasswordChangeForm,
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
    shop_id = form['shop_id']
    old_password = form['old_password']
    new_password = form['new_password']


    if user_id != request.user.id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse.does_not_exists_error()

        try:
            employment = Employment.objects.get(
                user_id=user_id,
                shop_id=shop_id,
            )
        except Employment.DoesNotExist:
            return JsonResponse.access_forbidden()

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
            'type': change_request.type,
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
    shop_id = form['shop_id']

    try:
        employment = Employment.objects.get(
            user_id=user_id,
            shop_id=shop_id,
        )
    except Employment.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    if user_id != request.user.id:
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return JsonResponse.does_not_exists_error()
    else:
        user = request.user

    user.first_name = form['first_name']
    user.middle_name = form['middle_name']
    user.last_name = form['last_name']
    user.phone_number = form['phone_number']
    user.email = form['email']


    employment.dt_hired = form['dt_hired']
    employment.position_id = form['position_id']
    employment.dt_fired = form['dt_fired']
    employment.tabel_code = form['tabel_code']
    employment.salary = form['salary'] if form['salary'] else 0


    if form['dt_fired']:

        #TODO убрать удаление расписания
        WorkerDayCashboxDetails.objects.filter(
            worker_day__employment=employment,
            worker_day__dt__gte=form['dt_fired'],
            is_vacancy=False,
        ).delete()

        WorkerDayCashboxDetails.objects.filter(
            worker_day__employment=employment,
            worker_day__dt__gte=form['dt_fired'],
            is_vacancy=True,
        ).update(
            dttm_deleted=timezone.now(),
            status=WorkerDayCashboxDetails.TYPE_DELETED,
        )


    user.save()
    employment.save()

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
    lambda_func=lambda x: WorkerDayChangeRequest.objects.get(id=x['request_id']).shop
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

@api_method('GET', check_permissions=False)
def get_worker_position_list(request):
    worker_positions = WorkerPosition.objects.all()
    return JsonResponse.success(Converter.convert(worker_positions, WorkerPosition))
