from src.util import utils
from src.db import models
from src.util.utils import ParseRequest, JsonResponse, api_method
from src.util.models_converter import UserConverter, WorkerDayConverter, WorkerDayChangeRequestConverter, WorkerDayChangeLogConverter
from .forms import GetCashiersSetForm, GetCashierTimetableForm


@utils.api_method('GET', GetCashiersSetForm)
def get_cashiers_set(request, form):
    users = list(
        models.User.objects.filter(
            shop_id=form.cleaned_data['shop_id'],
            dttm_deleted=None
        )
    )

    response = [UserConverter.convert(x) for x in users]

    return JsonResponse.success(response)


@api_method('GET', GetCashierTimetableForm)
def get_cashier_timetable(request, form):
    worker_id = form.cleaned_data['worker_id']
    from_dt = form.cleaned_data['from_dt']
    to_dt = form.cleaned_data['to_dt']

    worker_days = list(
        models.WorkerDay.objects.filter(
            worker_id=worker_id,
            dt__gte=from_dt,
            dt__lte=to_dt
        ).order_by(
            'dt'
        )
    )
    official_holidays = [
        x.date for x in models.OfficialHolidays.objects.filter(
            date__gte=from_dt,
            date__lte=to_dt
        )
    ]
    worker_day_change_requests = list(
        models.WorkerDayChangeRequest.objects.filter(
            worker_day_worker_id=worker_id,
            worker_day_dt__gte=from_dt,
            worker_day_dt__lte=to_dt
        ).order_by(
            '-worker_day_dt'
        )
    )
    worker_day_change_log = list(
        models.WorkerDayChangeLog.objects.filter(
            worker_day_worker_id=worker_id,
            worker_day_dt__gte=from_dt,
            worker_day_dt__lte=to_dt
        ).order_by(
            '-worker_day_dt'
        )
    )

    indicators_response = {
        'work_day_amount': utils.count(worker_days, lambda x: x.type == models.WorkerDay.Type.TYPE_WORKDAY.value),
        'holiday_amount': utils.count(worker_days, lambda x: x.type == models.WorkerDay.Type.TYPE_HOLIDAY.value),
        'sick_day_amount': utils.count(worker_days, lambda x: x.type == models.WorkerDay.Type.TYPE_SICK.value),
        'vacation_day_amount': utils.count(worker_days, lambda x: x.type == models.WorkerDay.Type.TYPE_VACATION.value),
        'work_day_in_holidays_amount': utils.count(worker_days, lambda x: x.type == models.WorkerDay.Type.TYPE_WORKDAY.value and x.dt in official_holidays),
        'change_amount': len(worker_day_change_log)
    }

    days_response = []
    for obj in worker_days:
        days_response.append({
            'day': WorkerDayConverter.convert(obj),
            'change_log': [WorkerDayChangeLogConverter.convert(x) for x in worker_day_change_log[:10]],
            'change_requests': [WorkerDayChangeRequestConverter.convert(x) for x in worker_day_change_requests[:10]]
        })

    response = {
        'indicators': indicators_response,
        'days': days_response
    }

    return JsonResponse.success(response)
