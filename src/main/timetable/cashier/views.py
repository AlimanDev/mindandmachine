from datetime import time, datetime, timedelta
from django.db.models import Avg, Q
from django.core.exceptions import ObjectDoesNotExist
import json

from src.db.models import (
    User,
    WorkerDay,
    WorkerDayChangeRequest,
    ProductionDay,
    WorkerCashboxInfo,
    WorkerConstraint,
    WorkType,
    WorkerDayCashboxDetails,
    WorkerPosition,
    Shop,
    Notifications,
)
from src.util.utils import (
    JsonResponse,
    api_method,
    check_group_hierarchy,
    GROUP_HIERARCHY,
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
    GetCashierInfoForm,
    SetWorkerDayForm,
    SetCashierInfoForm,
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
        shop_id(int): required = False
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
                | 'is_fixed_days': True/False,
                | 'phone_number'(str): номер телефона,
                | 'is_ready_for_overworkings': True/False (готов сотрудник к переработкам или нет),
                | 'tabel_code': табельный номер,
            }, ...
        ]}

    """
    response_users = []
    attachment_groups = [User.GROUP_STAFF, User.GROUP_OUTSOURCE if form['consider_outsource'] else None]
    shop_id = FormUtil.get_shop_id(request, form)
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
        shop_id(int): required = False

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
                | 'is_fixed_days': True/False,
                | 'phone_number'(str): номер телефона,
                | 'is_ready_for_overworkings': True/False (готов сотрудник к переработкам или нет),
                | 'tabel_code': табельный номер,
            }, ...
        ]}
    """
    dt_now = datetime.now() + timedelta(hours=3)
    shop_id = FormUtil.get_shop_id(request, form)
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


@api_method(
    'GET',
    GetCashierTimetableForm,
    groups=User.__all_groups__,
    lambda_func=lambda x: User.objects.filter(id__in=x['worker_id']).first()  # тут возможно будет косяк в будущем
)
def get_cashier_timetable(request, form):
    """
    Возвращает информацию о расписании сотрудника

    Args:
        method: GET
        url: /api/timetable/cashier/get_cashier_timetable
        worker_id(int): required = True
        from_dt(QOS_DATE): с какого числа смотреть расписание
        to_dt(QOS_DATE): по какое число
        format(str): 'raw' или 'excel'
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
    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    from_dt = form['from_dt']
    to_dt = form['to_dt']
    checkpoint = FormUtil.get_checkpoint(form)

    response = {}
    # todo: rewrite with 1 request instead 80
    for worker_id in form['worker_id']:
        worker_days_db = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
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
                wd_m.work_types_ids = [wd['work_types__id']] if wd['work_types__id'] else []
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

        # worker_day_change_requests = group_by(
        #     WorkerDayChangeRequest.objects.filter(
        #         worker_day_worker_id=worker_id,
        #         worker_day_dt__gte=from_dt,
        #         worker_day_dt__lte=to_dt
        #     ),
        #     group_key=lambda _: _.worker_day_id,
        #     sort_key=lambda _: _.worker_day_dt,
        #     sort_reverse=True
        # )

        worker_day_change_log = group_by(
            WorkerDay.objects.select_related('worker').filter(
                worker_id=worker_id,
                dt__gte=from_dt,
                dt__lte=to_dt,
                parent_worker_day__isnull=False,
                worker__attachment_group=User.GROUP_STAFF
            ),
            group_key=lambda _: _.id,
            sort_key=lambda _: _.dt,
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
                               worker_day_change_log.get(obj.id, [])[:10]],
                'change_requests': []
                # 'change_requests': [WorkerDayChangeRequestConverter.convert(x) for x in
                #                     worker_day_change_requests.get(obj.id, [])[:10]]
            })

        user = User.objects.get(id=worker_id)

        response[worker_id] = {
            'indicators': indicators_response,
            'days': days_response,
            'user': UserConverter.convert(user)
        }
    return JsonResponse.success(response)


@api_method(
    'GET',
    GetCashierInfoForm,
    groups=User.__all_groups__,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
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
                | 'is_fixed_days': True/False,
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
            'work_type': {x.id: WorkTypeConverter.convert(x) for x in work_types}
        }

    if 'constraints_info' in form['info']:
        constraints = WorkerConstraint.objects.filter(worker_id=worker.id, is_lite=request.is_mobile)
        response['constraints_info'] = [WorkerConstraintConverter.convert(x) for x in constraints]
        response['shop_times'] = {
            'tm_start': BaseConverter.convert_time(worker.shop.super_shop.tm_start),
            'tm_end': BaseConverter.convert_time(worker.shop.super_shop.tm_end)
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
    groups=User.__all_groups__,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
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


@api_method(
    'POST',
    SetWorkerDayForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
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

    dttm_work_start = datetime.combine(dt,
                                       form['tm_work_start'])  # на самом деле с фронта приходят время а не дата-время
    tm_work_end = form['tm_work_end']
    dttm_work_end = datetime.combine(form['dt'], tm_work_end) if tm_work_end > form['tm_work_start'] else \
        datetime.combine(dt + timedelta(days=1), tm_work_end)

    wd_args = {
        'dt': dt,
        'type': form['type'],
    }
    if WorkerDay.is_type_with_tm_range(form['type']):
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

    cashbox_updated = False

    # этот блок вводит логику относительно аутсорс сотрудников. у них выходных нет, поэтому их мы просто удаляем
    if old_wd and old_wd.worker.attachment_group == User.GROUP_OUTSOURCE:
        try:
            WorkerDayCashboxDetails.objects.filter(worker_day=old_wd).delete()
        except ObjectDoesNotExist:
            pass
        old_wd.delete()
        old_wd = None

    if worker.attachment_group == User.GROUP_STAFF \
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
                        work_type_id=item['cashBox_type'],
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
            cashbox_updated = True

            response['day'] = WorkerDayConverter.convert(new_worker_day)

    elif worker.attachment_group == User.GROUP_OUTSOURCE:
        worker.delete()

    response = {
        'action': action,
        'cashbox_updated': cashbox_updated
    }

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
            'prev_type': WorkerDayConverter.convert_type(obj.parent_worker_day.type),
            'prev_dttm_work_start': __work_dttm(obj.parent_worker_day.dttm_work_start),
            'prev_dttm_work_end': __work_dttm(obj.parent_worker_day.dttm_work_end),
        }

    shop_id = FormUtil.get_shop_id(request, form)
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

    child_worker_days = WorkerDay.objects.select_related('worker', 'parent_worker_day').filter(
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
    lambda_func=lambda x: WorkerDay.objects.get(id=x['worker_day_id']).worker
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


@api_method(
    'POST',
    SetCashierInfoForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def set_cashier_info_hard(request, form):
    """
    url: /api/timetable/cashier/set_cashier_info_hard
    """
    return set_cashier_info(request, form, False)


@api_method(
    'POST',
    SetCashierInfoForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def set_cashier_info_lite(request, form):
    """
    url: /api/timetable/cashier/set_cashier_info_lite
    """
    return set_cashier_info(request, form, True)


def set_cashier_info(request, form, is_lite=False):
    """
    Устанавливает заданные параметры кассиру

    Args:
        method: POST
        worker_id(int): required = True
        is_lite(bool): False -- с фронта, True -- с мобилы
        work_type(str): тип графика кассира (40часов, 5/2, etc). required = False
        cashbox_info(str): за какими типами касс может рабоать? required = False
        constraint(str):required = False
        comment(str): required = False
        sex(str): required = False
        is_fixed_hours(bool) required = False
        is_fixed_days(bool): required = False
        phone_number(str): required = False
        is_ready_for_overworkings(bool): required = False
        tabel_code(str): required = False
        position_department(int): required = False
        position_title(str): required = False, max_length=64

    Returns:
        {
            Сложный дикт
        }
    """
    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    response = {}

    if form.get('work_type'):
        worker.work_type = form['work_type']
        response['work_type'] = UserConverter.convert_work_type(worker.work_type)

    worker.extra_info = form.get('comment', '')
    worker.save()

    if form.get('cashbox_info'):
        work_types = {
            x.id: x for x in WorkType.objects.filter(shop_id=worker.shop_id)
        }

        new_active_cashboxes = []
        for obj in form['cashbox_info']:
            cb = work_types.get(obj.get('work_type_id'))
            if cb is not None:
                new_active_cashboxes.append((cb, obj.get('priority')))

        worker_cashbox_info = []
        WorkerCashboxInfo.objects.filter(worker_id=worker.id).update(is_active=False)
        for cashbox, priority in new_active_cashboxes:
            # worktype_forecast = WorkType.objects.get(id=cashbox.id)
            # mean_speed = 1
            # if worktype_forecast.do_forecast == WorkType.FORECAST_HARD:
            mean_speed = WorkerCashboxInfo.objects.filter(
                work_type__id=cashbox.id
            ).aggregate(Avg('mean_speed'))['mean_speed__avg']

            obj, created = WorkerCashboxInfo.objects.update_or_create(
                worker_id=worker.id,
                work_type_id=cashbox.id,
                defaults={
                    'is_active': True,
                },
            )
            if priority is not None:
                obj.priority = priority
                obj.save()

            if created:
                obj.mean_speed = mean_speed
                obj.save()
            worker_cashbox_info.append(obj)

        response['work_type'] = {x.id: WorkTypeConverter.convert(x) for x in work_types.values()}
        response['work_type_info'] = [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info]

    if form.get('constraint'):
        constraints = []
        WorkerConstraint.objects.filter(worker_id=worker.id).delete()
        for wd, times in form['constraint'].items():
            for tm in times:
                c = WorkerConstraint.objects.create(
                    worker_id=worker.id,
                    is_lite=is_lite,
                    weekday=wd,
                    tm=tm,
                )
                constraints.append(c)

        constraints_converted = {x: [] for x in range(7)}
        for c in constraints:
            constraints_converted[c.weekday].append(BaseConverter.convert_time(c.tm))

        response['constraint'] = constraints_converted

    if form.get('sex'):
        worker.sex = form['sex']
        response['sex'] = worker.sex

    if form.get('is_fixed_hours'):
        worker.is_fixed_hours = form['is_fixed_hours']
        response['is_fixed_hours'] = worker.is_fixed_hours

    if form.get('is_fixed_days'):
        worker.is_fixed_days = form['is_fixed_days']
        response['is_fixed_days'] = worker.is_fixed_days

    if form.get('phone_number'):
        worker.phone_number = form['phone_number']
        response['phone_number'] = worker.phone_number

    if form.get('is_ready_for_overworkings'):
        worker.is_ready_for_overworkings = form['is_ready_for_overworkings']
        response['is_ready_for_overworkings'] = worker.is_ready_for_overworkings

    if form.get('tabel_code'):
        worker.tabel_code = form['tabel_code']
        response['tabel_code'] = worker.tabel_code

    worker.save()

    return JsonResponse.success(response)


@api_method(
    'POST',
    CreateCashierForm,
    lambda_func=lambda x: False
)
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
        work_type(str): max_length = 3, required = True
        dt_hired(QOS_DATE): дата найма, required = True

    Note:
        также отправляет уведомление о том, что пользователь был создан

    Returns:
        {
            | 'id': id user'a,
            | 'username': ,
            | 'shop_id': ,
            | 'work_type': ,
            | 'first_name': ,
            | 'last_name': ,
            | 'avatar_url': ,
            | 'dt_hired': ,
            | 'dt_fired': ,
            | 'auto_timetable': ,
            | 'comment': ,
            | 'sex': ,
            | 'is_fixed_hours': ,
            | 'is_fixed_days': ,
            | 'phone_number': ,
            | 'is_ready_for_overworkings': ,
            | 'tabel_code':
        }
    """
    try:
        user = User.objects.create_user(username=form['username'], password=form['password'], email='q@q.com')
        user.first_name = form['first_name']
        user.middle_name = form['middle_name']
        user.last_name = form['last_name']
        user.work_type = form['work_type']
        user.shop = request.user.shop
        user.dt_hired = form['dt_hired']
        user.save()
    except:
        return JsonResponse.already_exists_error()

    send_notification('C', user, sender=request.user)

    return JsonResponse.success(UserConverter.convert(user))


@api_method(
    'POST',
    DublicateCashierTimetableForm,
    lambda_func=lambda x: User.objects.get(id=x['from_worker_id'])
)
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
    """
    from_worker_id = form['from_worker_id']
    to_worker_id = form['to_worker_id']
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    main_worker_days = WorkerDay.objects.qos_current_version().filter(
        worker_id=from_worker_id,
        dt__gte=from_dt,
        dt__lte=to_dt
    )
    main_worker_days_details = WorkerDayCashboxDetails.objects.qos_current_version().filter(
        worker_day__in=main_worker_days
    )

    trainee_worker_days = WorkerDay.objects.qos_current_version().filter(
        worker_id=to_worker_id,
        dt__gte=from_dt,
        dt__lte=to_dt
    )
    WorkerDayCashboxDetails.objects.filter(worker_day__in=trainee_worker_days).delete()
    trainee_worker_days.delete()

    wds_list_to_create = []
    wdcds_list_to_create = []

    try:
        for blank_day in main_worker_days:
            new_wd = WorkerDay(
                worker_id=to_worker_id,
                dt=blank_day.dt,
                type=blank_day.type,
                dttm_work_start=blank_day.dttm_work_start,
                dttm_work_end=blank_day.dttm_work_end,
            )
            wds_list_to_create.append(new_wd)
            new_wdcds = main_worker_days_details.filter(worker_day=new_wd).order_by('id').first()
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

        WorkerDay.objects.bulk_create(wds_list_to_create)
        WorkerDayCashboxDetails.objects.bulk_create(wdcds_list_to_create)
    except Exception:
        return JsonResponse.internal_error('Ошибка при дублировании расписания.')

    return JsonResponse.success()


@api_method(
    'POST',
    DeleteCashierForm,
    lambda_func=lambda x: User.objects.get(id=x['user_id'])
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
        errors = check_group_hierarchy(user, request.user)
        if errors:
            return errors
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
    groups=User.__all_groups__,
    lambda_func=lambda x: User.objects.get(id=x['user_id'])
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
            errors = check_group_hierarchy(user, request.user)
            if errors:
                return errors
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
    'POST',
    ChangeCashierInfo,
    groups=User.__allowed_to_modify__,
    lambda_func=lambda x: User.objects.get(id=x['user_id']),
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
            errors = check_group_hierarchy(user, request.user)
            if errors:
                return errors
        except User.DoesNotExist:
            return JsonResponse.does_not_exists_error()
    else:
        user = request.user

    if form['group']:
        if GROUP_HIERARCHY[request.user.group] < GROUP_HIERARCHY[form['group']]:
            return JsonResponse.access_forbidden('У вас недостаточно прав доступа для изменения данной группы.')
        user.group = form['group']

    if form['first_name']:
        user.first_name = form['first_name']
    if form['middle_name']:
        user.middle_name = form['middle_name']
    if form['last_name']:
        user.last_name = form['last_name']
    if form['tabel_code']:
        user.tabel_code = form['tabel_code']
    if form['phone_number']:
        user.phone_number = form['phone_number']
    if form['email']:
        user.email = form['email']
    if form['dt_hired']:
        user.dt_hired = form['dt_hired']
    if form['dt_fired']:
        user.dt_fired = form['dt_fired']

    user.save()

    return JsonResponse.success()

# views for making requests for changing worker day from mobile application


@api_method(
    'GET',
    GetWorkerChangeRequestsForm,
    groups=User.__all_groups__,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
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


@api_method(
    'POST',
    SetWorkerDayForm,
    check_permissions=False,
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
    Notifications.objects.filter(object_id__in=existing_requests.values_list('id')).delete()
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
    groups=User.__allowed_to_modify__,
    lambda_func=lambda x: WorkerDayChangeRequest.objects.get(id=x['request_id']).worker
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

        Notifications.objects.create(
            to_worker_id=change_request.worker_id,
            type=Notifications.TYPE_INFO,
            text=new_notification_text+'одобрен.'
        )
        change_request.status_type = WorkerDayChangeRequest.TYPE_APPROVED

    elif action == 'D':
        Notifications.objects.create(
            to_worker_id=change_request.worker_id,
            type=Notifications.TYPE_INFO,
            text=new_notification_text + 'отклонен.'
        )
        change_request.status_type = WorkerDayChangeRequest.TYPE_DECLINED
    else:
        return JsonResponse.internal_error('Неизвестное дейсвтие')

    change_request.save()
    Notifications.objects.filter(object_id=change_request.id).delete()

    return JsonResponse.success()