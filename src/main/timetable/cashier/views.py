from datetime import time, datetime, timedelta

from src.db.models import User, WorkerDay, WorkerDayChangeRequest, WorkerDayChangeLog, OfficialHolidays, WorkerCashboxInfo, WorkerConstraint, CashboxType, WorkerDayCashboxDetails
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import UserConverter, WorkerDayConverter, WorkerDayChangeRequestConverter, WorkerDayChangeLogConverter, WorkerConstraintConverter, \
    WorkerCashboxInfoConverter, CashboxTypeConverter, BaseConverter
from src.util.collection import group_by, count, range_u

from .forms import GetCashierTimetableForm, GetCashierInfoForm, SetWorkerDayForm, SetCashierInfoForm, GetWorkerDayForm
from . import utils


@api_method('GET')
def get_cashiers_list(request):
    users = list(
        User.objects.filter(
            shop_id=request.user.shop_id,
            dttm_deleted=None
        ).order_by(
            'last_name', 'first_name'
        )
    )

    response = [UserConverter.convert(x) for x in users]

    return JsonResponse.success(response)


@api_method('GET', GetCashierTimetableForm)
def get_cashier_timetable(request, form):
    if form['format'] == 'excel':
        return JsonResponse.value_error('Excel is not supported yet')

    from_dt = form['from_dt']
    to_dt = form['to_dt']

    response = {}
    for worker_id in form['worker_id']:
        worker_days = list(
            WorkerDay.objects.filter(
                worker_id=worker_id,
                dt__gte=from_dt,
                dt__lte=to_dt
            ).order_by(
                'dt'
            )
        )
        official_holidays = [
            x.date for x in OfficialHolidays.objects.filter(
                date__gte=from_dt,
                date__lte=to_dt
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
    cashboxes_types = []
    for x in WorkerDayCashboxDetails.objects.select_related('on_cashbox', 'on_cashbox__type').filter(worker_day=wd):
        details.append({
            'tm_from': BaseConverter.convert_time(x.tm_from),
            'tm_to': BaseConverter.convert_time(x.tm_to),
            'cashbox_type': x.on_cashbox.type_id
        })
        cashboxes_types.append(CashboxTypeConverter.convert(x.on_cashbox.type))

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

        day_change_args = utils.prepare_worker_day_change_create_args(request, form, day)
        utils.prepare_worker_day_update_obj(form, day)

        WorkerDayChangeLog.objects.create(**day_change_args)
        day.save()

        action = 'update'
    except WorkerDay.DoesNotExist:
        day_args = utils.prepare_worker_day_create_args(form, worker)
        day = WorkerDay.objects.create(**day_args)

        action = 'create'

    response = {
        'day': WorkerDayConverter.convert(day),
        'action': action
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
        worker.save()

        response['work_type'] = UserConverter.convert_work_type(worker.work_type)

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
            obj, created = WorkerCashboxInfo.objects.update_or_create(
                worker_id=worker.id,
                cashbox_type_id=cashbox.id,
                defaults={
                    'is_active': True
                }
            )
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

    return JsonResponse.success(response)
