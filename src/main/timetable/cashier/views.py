from datetime import time, datetime, timedelta
from django.db.models import Avg
from django.forms.models import model_to_dict
import json

from src.db.models import (
    User,
    WorkerDay,
    WorkerDayChangeRequest,
    WorkerDayChangeLog, ProductionDay,
    WorkerCashboxInfo,
    WorkerConstraint,
    CashboxType,
    WorkerDayCashboxDetails,
    WorkerPosition,
    Shop,
)
from src.util.utils import JsonResponse, api_method
from src.util.forms import FormUtil
from src.util.models_converter import (
    UserConverter,
    WorkerDayConverter,
    WorkerDayChangeRequestConverter,
    WorkerDayChangeLogConverter,
    WorkerConstraintConverter,
    WorkerCashboxInfoConverter,
    CashboxTypeConverter,
    BaseConverter
)
from src.util.collection import group_by, count, range_u, group_by_object

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
    SetWorkerDaysForm
)
from . import utils
from src.main.other.notification.utils import send_notification


@api_method('GET', GetCashiersListForm)
def get_cashiers_list(request, form):
    users = []
    shop_id = FormUtil.get_shop_id(request, form)
    # todo: прочекать что все ок
    for u in User.objects.filter(shop_id=shop_id).order_by('last_name', 'first_name'):
        if u.dt_hired is None or u.dt_hired <= form['dt_hired_before']:
            if u.dt_fired is None or u.dt_fired >= form['dt_fired_after']:
                users.append(u)

    return JsonResponse.success([UserConverter.convert(x) for x in users])


@api_method('GET', GetCashiersListForm)
def get_not_working_cashiers_list(request, form):
    dt_now = datetime.now() + timedelta(hours=3)
    shop_id = FormUtil.get_shop_id(request, form)

    users_not_working_today = []
    for u in WorkerDay.objects.select_related('worker').filter(dt=dt_now.date(), worker__shop_id=shop_id). \
            exclude(type=WorkerDay.Type.TYPE_WORKDAY.value). \
            order_by('worker__last_name', 'worker__first_name'):
        if u.worker.dt_hired is None or u.worker.dt_hired <= form['dt_hired_before']:
            if u.worker.dt_fired is None or u.worker.dt_fired >= form['dt_fired_after']:
                users_not_working_today.append(u.worker)

    return JsonResponse.success([UserConverter.convert(x) for x in users_not_working_today])


@api_method(
    'GET',
    GetCashierTimetableForm,
    groups=User.__all_groups__,
    lambda_func=lambda x: Shop.objects.get(id=x['shop_id'])
)
def get_cashier_timetable(request, form):
    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    from_dt = form['from_dt']
    to_dt = form['to_dt']

    response = {}
    # todo: rewrite with 1 request instead 80
    for worker_id in form['worker_id']:
        worker_days_db = WorkerDay.objects.filter(
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
            'tm_work_start',
            'tm_work_end',
            'tm_break_start',
            'is_manual_tuning',
            'cashbox_types__id',
        )

        worker_days = []
        worker_days_mask = {}
        for wd in worker_days_db:
            if (wd['id'] in worker_days_mask) and wd['cashbox_types__id']:
                ind = worker_days_mask[wd['id']]
                worker_days[ind].cashbox_types_ids.append(wd['cashbox_types__id'])
            else:
                worker_days_mask[wd['id']] = len(worker_days)
                wd_m = WorkerDay(
                    id=wd['id'],
                    type=wd['type'],
                    dttm_added=wd['dttm_added'],
                    dt=wd['dt'],
                    worker_id=wd['worker_id'],
                    tm_work_start=wd['tm_work_start'],
                    tm_work_end=wd['tm_work_end'],
                    tm_break_start=wd['tm_break_start'],
                    is_manual_tuning=wd['is_manual_tuning'],
                )
                wd_m.cashbox_types_ids = [wd['cashbox_types__id']] if wd['cashbox_types__id'] else []
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

        worker_day_change_requests = group_by(
            WorkerDayChangeRequest.objects.filter(
                worker_day_worker_id=worker_id,
                worker_day_dt__gte=from_dt,
                worker_day_dt__lte=to_dt
            ),
            group_key=lambda _: _.worker_day_id,
            sort_key=lambda _: _.worker_day_dt,
            sort_reverse=True
        )

        worker_day_change_log = group_by(
            WorkerDayChangeLog.objects.filter(
                worker_day_worker_id=worker_id,
                worker_day_dt__gte=from_dt,
                worker_day_dt__lte=to_dt
            ),
            group_key=lambda _: _.worker_day_id,
            sort_key=lambda _: _.worker_day_dt,
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
                'change_requests': [WorkerDayChangeRequestConverter.convert(x) for x in
                                    worker_day_change_requests.get(obj.id, [])[:10]]
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
    response = {}

    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    if 'general_info' in form['info']:
        response['general_info'] = UserConverter.convert(worker)

    if 'cashbox_type_info' in form['info']:
        worker_cashbox_info = WorkerCashboxInfo.objects.filter(worker_id=worker.id, is_active=True)
        cashbox_types = CashboxType.objects.filter(shop_id=worker.shop_id)
        response['cashbox_type_info'] = {
            'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info],
            'cashbox_type': {x.id: CashboxTypeConverter.convert(x) for x in cashbox_types}
        }

    if 'constraints_info' in form['info']:
        constraints = WorkerConstraint.objects.filter(worker_id=worker.id)
        response['constraints_info'] = [WorkerConstraintConverter.convert(x) for x in constraints]

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
    worker_id = form['worker_id']
    dt = form['dt']

    try:
        wd = WorkerDay.objects.get(worker_id=worker_id, dt=dt)
    except WorkerDay.DoesNotExist:
        return JsonResponse.does_not_exists_error()
    except:
        return JsonResponse.internal_error()

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
    for x in WorkerDayCashboxDetails.objects.select_related('on_cashbox', 'cashbox_type').filter(worker_day=wd):
        details.append({
            'tm_from': BaseConverter.convert_time(x.tm_from),
            'tm_to': BaseConverter.convert_time(x.tm_to),
            'cashbox_type': x.cashbox_type_id,
        })
        cashboxes_types[x.cashbox_type_id] = CashboxTypeConverter.convert(x.cashbox_type)

    return JsonResponse.success({
        'day': WorkerDayConverter.convert(wd),
        'work_hours': work_hours,
        'details': details,
        'cashbox_types': cashboxes_types
    })


@api_method(
    'POST',
    SetWorkerDaysForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def set_worker_days(request, form):
    worker = form['worker_id']

    # интервал дней из формы
    form_dates = []
    for dt in range(int((form['dt_end'] - form['dt_begin']).days) + 1):
        form_dates.append(form['dt_begin'] + timedelta(dt))

    existed_worker_days = WorkerDay.objects.filter(
        worker=worker,
        dt__gte=form['dt_begin'],
        dt__lte=form['dt_end']
    )
    # обновляем worker_day, если есть
    change_log = {}
    for worker_day in existed_worker_days:
        form_dates.remove(worker_day.dt)
        change_log[worker_day.dt] = model_to_dict(
            worker_day,
            fields=[
                'dt',
                'type',
                'tm_work_start',
                'tm_work_end',
            ]
        )
        # обновляем дни и удаляем details для этих дней
        worker_day.type = form['type']
        worker_day.tm_work_start = form['tm_work_start']
        worker_day.tm_work_end = form['tm_work_end']
        worker_day.save()
        WorkerDayCashboxDetails.objects.filter(worker_day=worker_day).delete()

    WorkerDayCashboxDetails.objects.bulk_create([
        WorkerDayCashboxDetails(
            worker_day=worker_day,
            cashbox_type_id=form['cashbox_type'],
            tm_from=form['tm_work_start'],
            tm_to=form['tm_work_end']
        ) for worker_day in existed_worker_days
    ])

    updated_worker_days = WorkerDay.objects.filter(
        worker=worker,
        dt__gte=form['dt_begin'],
        dt__lte=form['dt_end']
    )
    WorkerDayChangeLog.objects.bulk_create([
        WorkerDayChangeLog(
            worker_day=worker_day,
            worker_day_worker=worker_day.worker,
            worker_day_dt=worker_day.dt,
            from_type=change_log.get(worker_day.dt)['type'],
            from_tm_work_start=change_log.get(worker_day.dt)['tm_work_start'],
            from_tm_work_end=change_log.get(worker_day.dt)['tm_work_end'],
            to_type=worker_day.type,
            to_tm_work_start=worker_day.tm_work_start,
            to_tm_work_end=worker_day.tm_work_end,
            changed_by=request.user
        ) for worker_day in updated_worker_days
    ])
    # незаполненные дни
    filled_days = WorkerDay.objects.bulk_create([
        WorkerDay(
            worker=worker,
            dt=day,
            type=form['type'],
            worker_shop_id=worker.shop_id,
            tm_work_start=form['tm_work_start'],
            tm_work_end=form['tm_work_end'],
        ) for day in form_dates
    ])
    WorkerDayCashboxDetails.objects.bulk_create([
        WorkerDayCashboxDetails(
            worker_day=worker_day,
            cashbox_type_id=form['cashbox_type'],
            tm_from=form['tm_work_start'],
            tm_to=form['tm_work_end']
        ) for worker_day in filled_days
    ])

    return JsonResponse.success({})


@api_method(
    'POST',
    SetWorkerDayForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def set_worker_day(request, form):
    if form['details']:
        details = json.loads(form['details'])
    else:
        details = []

    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    try:
        day = WorkerDay.objects.get(worker_id=worker.id, dt=form['dt'])

        utils.prepare_worker_day_update_obj(form, day)
        day.save()

        action = 'update'
    except WorkerDay.DoesNotExist:

        day_args = utils.prepare_worker_day_create_args(form, worker)
        day = WorkerDay.objects.create(**day_args)

        action = 'create'

    day_change_args = utils.prepare_worker_day_change_create_args(request, form, day)
    WorkerDayChangeLog.objects.create(**day_change_args)

    # cashbox_type_id = form.get('cashbox_type')
    cashbox_updated = False
    try:
        WorkerDayCashboxDetails.objects.filter(worker_day=day).delete()
        if day.type == WorkerDay.Type.TYPE_WORKDAY.value:
            if len(details):
                for item in details:
                    WorkerDayCashboxDetails.objects.create(
                        cashbox_type_id=item['cashBox_type'],
                        worker_day=day,
                        tm_from=item['tm_from'],
                        tm_to=item['tm_to']
                    )
            else:
                cashbox_type_id = form.get('cashbox_type')
                WorkerDayCashboxDetails.objects.create(
                    cashbox_type_id=cashbox_type_id,
                    worker_day=day,
                    tm_from=day.tm_work_start,
                    tm_to=day.tm_work_end
                )
            cashbox_updated = True
    except:
        pass

    response = {
        'day': WorkerDayConverter.convert(day),
        'action': action,
        'cashbox_updated': cashbox_updated
    }

    return JsonResponse.success(response)


@api_method(
    'POST',
    SetCashierInfoForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def set_cashier_info(request, form):
    try:
        worker = User.objects.get(id=form['worker_id'])
    except User.DoesNotExist:
        return JsonResponse.value_error('Invalid worker_id')

    response = {}

    if form.get('work_type') is not None:
        worker.work_type = form['work_type']
        response['work_type'] = UserConverter.convert_work_type(worker.work_type)

    worker.extra_info = form.get('comment', '')
    worker.save()

    if form.get('cashbox_info') is not None:
        cashbox_types = {
            x.id: x for x in CashboxType.objects.filter(
            shop_id=worker.shop_id
        )
        }

        new_active_cashboxes = []
        for obj in form['cashbox_info']:
            cb = cashbox_types.get(obj.get('cashbox_type_id'))
            if cb is not None:
                new_active_cashboxes.append((cb, obj.get('priority')))

        worker_cashbox_info = []
        WorkerCashboxInfo.objects.filter(worker_id=worker.id).update(is_active=False)
        for cashbox, priority in new_active_cashboxes:
            cashboxtype_forecast = CashboxType.objects.get(id=cashbox.id)
            mean_speed = 1
            if cashboxtype_forecast.do_forecast == CashboxType.FORECAST_HARD:
                mean_speed = WorkerCashboxInfo.objects.filter(
                    cashbox_type__id=cashbox.id
                ).aggregate(Avg('mean_speed'))['mean_speed__avg']
            obj, created = WorkerCashboxInfo.objects.update_or_create(
                worker_id=worker.id,
                cashbox_type_id=cashbox.id,
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

        response['cashbox_type'] = {x.id: CashboxTypeConverter.convert(x) for x in cashbox_types.values()}
        response['cashbox_type_info'] = [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info]

    if form.get('constraint') is not None:
        constraints = []
        WorkerConstraint.objects.filter(worker_id=worker.id).delete()
        for wd, times in form['constraint'].items():
            for tm in times:
                c = WorkerConstraint.objects.create(worker_id=worker.id, weekday=wd, tm=tm)
                constraints.append(c)

        constraints_converted = {x: [] for x in range(7)}
        for c in constraints:
            constraints_converted[c.weekday].append(BaseConverter.convert_time(c.tm))

        response['constraint'] = constraints_converted

    if form.get('sex') is not None:
        worker.sex = form['sex']
        response['sex'] = worker.sex

    if form.get('is_fixed_hours') is not None:
        worker.is_fixed_hours = form['is_fixed_hours']
        response['is_fixed_hours'] = worker.is_fixed_hours

    if form.get('is_fixed_days') is not None:
        worker.is_fixed_days = form['is_fixed_days']
        response['is_fixed_days'] = worker.is_fixed_days

    if form.get('phone_number') is not None:
        worker.phone_number = form['phone_number']
        response['phone_number'] = worker.phone_number

    if form.get('is_ready_for_overworkings') is not None:
        worker.is_ready_for_overworkings = form['is_ready_for_overworkings']
        response['is_ready_for_overworkings'] = worker.is_ready_for_overworkings

    if form.get('tabel_code') is not None:
        worker.tabel_code = form['tabel_code']
        response['tabel_code'] = worker.tabel_code

    if form.get('position_title') is not None \
            and form.get('position_department') is not None:
        department = Shop.objects.get(id=form['position_department'])
        position, created = WorkerPosition.objects.get_or_create(
            title=form['position_title'],
            department=department,
        )
        worker.position = position
        response['position'] = {
            'title': form['position_title'],
            'department': form['position_department'],
        }

    worker.save()

    return JsonResponse.success(response)


@api_method(
    'POST',
    CreateCashierForm,
    lambda_func=lambda x: False
)
def create_cashier(request, form):
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
    lambda_func=lambda x: User.objects.get(id=x['main_worker_id'])
)
def dublicate_cashier_table(request, form):
    main_worker = form['main_worker_id']
    trainee_worker = form['trainee_worker_id']
    dt_begin = form['dt_begin']
    dt_end = form['dt_end']

    main_worker_days = WorkerDay.objects.prefetch_related('workerdaycashboxdetails_set').filter(
        worker=main_worker,
        dt__gte=dt_begin,
        dt__lte=dt_end
    )
    main_worker_days_details = WorkerDayCashboxDetails.objects.filter(worker_day__in=main_worker_days)

    # проверка на наличие дней у стажера
    trainee_worker_days = group_by_object(
        WorkerDay.objects.prefetch_related('workerdaycashboxdetails_set').filter(
            worker=trainee_worker,
            dt__gte=dt_begin,
            dt__lte=dt_end
        ),
        group_key=lambda _: _.dt,
    )

    old_values = {}
    for main_worker_day in main_worker_days:
        if main_worker_day.dt in trainee_worker_days:
            # записываем аргументы для лога до изменения WorkerDay
            trainee_worker_day = trainee_worker_days.get(main_worker_day.dt)
            old_values[trainee_worker_day.dt] = model_to_dict(
                trainee_worker_day,
                fields=[
                    'dt',
                    'type',
                    'tm_work_start',
                    'tm_work_end',
                    'tm_break_start'
                ]
            )

            # обновляем дни и удаляем details для этих дней
            trainee_worker_day.type = main_worker_day.type
            trainee_worker_day.worker_shop = main_worker_day.worker_shop
            trainee_worker_day.tm_work_start = main_worker_day.tm_work_start
            trainee_worker_day.tm_work_end = main_worker_day.tm_work_end
            trainee_worker_day.tm_break_start = main_worker_day.tm_break_start
            trainee_worker_day.save()

            main_worker_days = main_worker_days.exclude(dt=main_worker_day.dt)

    WorkerDayCashboxDetails.objects.filter(worker_day__in=trainee_worker_days.values()).delete()

    WorkerDayChangeLog.objects.bulk_create([
        WorkerDayChangeLog(
            worker_day=trainee_worker_days.get(trainee_worker_day_dt),
            worker_day_worker=trainee_worker_days.get(trainee_worker_day_dt).worker,
            worker_day_dt=trainee_worker_day_dt,
            from_type=old_values.get(trainee_worker_day.dt)['type'],
            from_tm_work_start=old_values.get(trainee_worker_day.dt)['tm_work_start'],
            from_tm_work_end=old_values.get(trainee_worker_day.dt)['tm_work_end'],
            from_tm_break_start=old_values.get(trainee_worker_day.dt)['tm_break_start'],
            to_type=trainee_worker_days.get(trainee_worker_day_dt).type,
            to_tm_work_start=trainee_worker_days.get(trainee_worker_day_dt).tm_work_start,
            to_tm_work_end=trainee_worker_days.get(trainee_worker_day_dt).tm_work_end,
            to_tm_break_start=trainee_worker_days.get(trainee_worker_day_dt).tm_break_start,
            changed_by=request.user
        ) for trainee_worker_day_dt in trainee_worker_days
    ])

    # незаполненные дни
    WorkerDay.objects.bulk_create([
        WorkerDay(
            worker=trainee_worker,
            dt=blank_day.dt,
            type=blank_day.type,
            worker_shop=blank_day.worker_shop,
            tm_work_start=blank_day.tm_work_start,
            tm_work_end=blank_day.tm_work_end,
            tm_break_start=blank_day.tm_break_start
        ) for blank_day in main_worker_days
    ])

    full_trainee_worker_days = group_by_object(
        WorkerDay.objects.prefetch_related('workerdaycashboxdetails_set').filter(
            worker=trainee_worker,
            dt__gte=dt_begin,
            dt__lte=dt_end
        ),
        group_key=lambda _: _.dt,
    )

    WorkerDayCashboxDetails.objects.bulk_create([
        WorkerDayCashboxDetails(
            worker_day=full_trainee_worker_days.get(day_detail.worker_day.dt),
            on_cashbox=day_detail.on_cashbox,
            cashbox_type=day_detail.cashbox_type,
            tm_from=day_detail.tm_from,
            tm_to=day_detail.tm_to
        ) for day_detail in main_worker_days_details
    ])

    return JsonResponse.success({})


@api_method(
    'POST',
    DeleteCashierForm,
    lambda_func=lambda x: User.objects.get(id=x['user_id'])
)
def delete_cashier(request, form):
    try:
        user = User.objects.get(id=form['user_id'])
    except User.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    user.dt_fired = form['dt_fired']
    user.save()

    send_notification('D', user, sender=request.user)

    return JsonResponse.success(UserConverter.convert(user))
