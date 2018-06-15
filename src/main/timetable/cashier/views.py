from datetime import time, datetime, timedelta
from django.db.models import Avg

from src.db.models import (
    User,
    WorkerDay,
    WorkerDayChangeRequest,
    WorkerDayChangeLog, ProductionDay,
    WorkerCashboxInfo,
    WorkerConstraint,
    CashboxType,
    WorkerDayCashboxDetails,
    Cashbox,
    WorkerPosition,
    Shop,
)
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import UserConverter, WorkerDayConverter, WorkerDayChangeRequestConverter, WorkerDayChangeLogConverter, WorkerConstraintConverter, \
    WorkerCashboxInfoConverter, CashboxTypeConverter, BaseConverter
from src.util.collection import group_by, count, range_u

from .forms import GetCashierTimetableForm, GetCashierInfoForm, SetWorkerDayForm, SetCashierInfoForm, GetWorkerDayForm, CreateCashierForm, DeleteCashierForm, GetCashiersListForm
from . import utils


@api_method('GET', GetCashiersListForm)
def get_cashiers_list(request, form):
    users = []
    if form['shop_id']:
        shop_id = form['shop_id']
    else:
        shop_id = request.user.shop_id
    for u in User.objects.filter(shop_id=shop_id).order_by('last_name', 'first_name'):
        if u.dt_hired is None or u.dt_hired <= form['dt_hired_before']:
            if u.dt_fired is None or u.dt_fired >= form['dt_fired_after']:
                users.append(u)

    return JsonResponse.success([UserConverter.convert(x) for x in users])


@api_method('GET', GetCashierTimetableForm)
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
            'work_day_in_holidays_amount': count(worker_days, lambda x: x.type == WorkerDay.Type.TYPE_WORKDAY.value and x.dt in official_holidays),
            'change_amount': len(worker_day_change_log)
        }

        days_response = []
        for obj in worker_days:
            days_response.append({
                'day': WorkerDayConverter.convert(obj),
                'change_log': [WorkerDayChangeLogConverter.convert(x) for x in worker_day_change_log.get(obj.id, [])[:10]],
                'change_requests': [WorkerDayChangeRequestConverter.convert(x) for x in worker_day_change_requests.get(obj.id, [])[:10]]
            })

        user = User.objects.get(id=worker_id)

        response[worker_id] = {
            'indicators': indicators_response,
            'days': days_response,
            'user': UserConverter.convert(user)
        }

    return JsonResponse.success(response)


@api_method('GET', GetCashierInfoForm)
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
            times = [dttm for dttm in range_u(dttm_from, dttm_to, dttm_step, False) if dttm.time() not in constraint_times]
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


@api_method('GET', GetWorkerDayForm)
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


@api_method('POST', SetWorkerDayForm)
def set_worker_day(request, form):
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

    cashbox_type_id = form.get('cashbox_type')
    cashbox_updated = False
    try:
        if day.type == WorkerDay.Type.TYPE_WORKDAY.value:
            if cashbox_type_id is not None:
                # new_cashbox = Cashbox.objects.filter(type_id=new_cashbox_type_id).first()
                # check if could work
                # WorkerCashboxInfo.objects.get(worker_id=day.worker_id, cashbox_type_id=new_cashbox.type_id, is_active=True)

                # todo: understand idea of updating -- seems must be deleted
                rows = WorkerDayCashboxDetails.objects.filter(worker_day=day).update(
                    cashbox_type_id=cashbox_type_id,
                    tm_from=day.tm_work_start,
                    tm_to=day.tm_work_end
                )
                if rows == 0:
                    WorkerDayCashboxDetails.objects.create(
                        cashbox_type_id=cashbox_type_id,
                        worker_day=day,
                        tm_from=day.tm_work_start,
                        tm_to=day.tm_work_end
                    )
                cashbox_updated = True
        else:
            rows = WorkerDayCashboxDetails.objects.filter(worker_day=day).delete()
            cashbox_updated = rows > 0
    except:
        pass

    response = {
        'day': WorkerDayConverter.convert(day),
        'action': action,
        'cashbox_updated': cashbox_updated
    }

    return JsonResponse.success(response)


@api_method('POST', SetCashierInfoForm)
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
                new_active_cashboxes.append(cb)

        worker_cashbox_info = []
        WorkerCashboxInfo.objects.filter(worker_id=worker.id).update(is_active=False)
        for cashbox in new_active_cashboxes:
            cashboxtype_forecast = CashboxType.objects.get(id=cashbox.id)
            mean_speed = 1
            if cashboxtype_forecast.do_forecast == CashboxType.FORECAST_HARD:
                mean_speed = WorkerCashboxInfo.objects\
                    .filter(cashbox_type__id=cashbox.id)\
                    .aggregate(Avg('mean_speed'))['mean_speed__avg']

            obj, created = WorkerCashboxInfo.objects.update_or_create(
                worker_id=worker.id,
                cashbox_type_id=cashbox.id,
                defaults={
                    'is_active': True,
                },
            )
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

    if form.get('position_title') is not None\
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


@api_method('POST', CreateCashierForm)
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

    return JsonResponse.success(UserConverter.convert(user))


@api_method('POST', DeleteCashierForm)
def delete_cashier(request, form):
    try:
        user = User.objects.get(id=form['user_id'])
    except User.DoesNotExist:
        return JsonResponse.does_not_exists_error()

    user.dt_fired = form['dt_fired']
    user.save()

    return JsonResponse.success(UserConverter.convert(user))
