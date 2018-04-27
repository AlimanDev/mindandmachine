import json
import urllib.request

from datetime import datetime

from django.conf import settings
from django.views.decorators.csrf import csrf_exempt

from src.db.models import Timetable, User, CashboxType, PeriodDemand, WorkerConstraint, WorkerCashboxInfo, WorkerDay, WorkerDayCashboxDetails
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
    try:
        tt = Timetable.objects.create(
            shop_id=shop_id,
            dt=form['dt'],
            status=Timetable.Status.PROCESSING.value,
            dttm_status_change=datetime.now()
        )
    except:
        return JsonResponse.already_exists_error()

    periods = PeriodDemand.objects.select_related(
        'cashbox_type'
    ).filter(
        cashbox_type__shop_id=shop_id,
        type__in=[PeriodDemand.Type.LONG_FORECAST.value, PeriodDemand.Type.SHORT_FORECAST.value]
    )

    constraints = group_by(
        collection=WorkerConstraint.objects.select_related('worker').filter(worker__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )

    worker_cashbox_info = group_by(
        collection=WorkerCashboxInfo.objects.select_related('cashbox_type').filter(cashbox_type__shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )

    worker_day = group_by(
        collection=WorkerDay.objects.filter(worker_shop_id=shop_id),
        group_key=lambda x: x.worker_id
    )

    data = {
        'start_dt': BaseConverter.convert_date(tt.dt),
        'timetable_id': tt.id,
        'cashbox_types': [CashboxTypeConverter.convert(x) for x in CashboxType.objects.filter(shop_id=shop_id)],
        'demand': [PeriodDemandConverter.convert(x) for x in periods],
        'cashiers': [
            {
                'general_info': UserConverter.convert(u),
                'constraints_info': [WorkerConstraintConverter.convert(x) for x in constraints.get(u.id, [])],
                'worker_cashbox_info': [WorkerCashboxInfoConverter.convert(x) for x in worker_cashbox_info.get(u.id, [])],
                'workdays': [WorkerDayConverter.convert_type(x.type) for x in worker_day.get(u.id, [])]
            } for u in User.objects.filter(shop_id=shop_id)
        ]
    }

    data = json.dumps(data).encode('ascii')
    req = urllib.request.Request('http://149.154.64.204/', data=data, headers={'content-type': 'application/json'})
    with urllib.request.urlopen(req) as response:
        data = response.read().decode('utf-8')

    return JsonResponse.success()


@api_method('POST', DeleteTimetableForm)
def delete_timetable(request, form):
    shop_id = FormUtil.get_shop_id(request, form)

    dt = form['dt']
    dt_now = datetime.now()

    if dt.month != dt_now.month and dt < dt_now:
        return JsonResponse.value_error('Cannot delete past month')

    count, _ = Timetable.objects.filter(shop_id=shop_id, dt=form['dt']).delete()

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
