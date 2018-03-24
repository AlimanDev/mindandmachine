from . import utils
from src.db import models
from .utils import ParseRequest, JsonResponse


def timetable_cashier_get_cashiers_set(request):
    shop_id, e = ParseRequest.get_simple_param(request.GET, 'shop_id', int)
    if e is not None:
        return e

    response_data = []
    for w in models.User.objects.filter(shop_id=shop_id, dttm_deleted=None):
        response_data.append({
            'user_id': w.id,
            'first_name': w.first_name,
            'last_name': w.last_name,
            'avatar_url': w.avatar.url if w.avatar else None
        })
    return JsonResponse.success(response_data)


def timetable_cashier_get_cashier_timetable(request):
    worker_id, e = ParseRequest.get_simple_param(request.GET, 'worker_id', int)
    from_dt, e = ParseRequest.get_simple_param(request.GET, 'from_dt', utils.parse_date, e)
    to_dt, e = ParseRequest.get_simple_param(request.GET, 'to_dt', utils.parse_date, e)
    to_file_format, e = ParseRequest.get_match_param(request.GET, 'format', None, ['raw', 'excel'], e)
    if e is not None:
        return e

    if from_dt > to_dt:
        return JsonResponse.value_error('from_dt have to be less than to_dt')

    days = list(models.WorkerDay.objects.filter(worker=worker_id, dt__gte=from_dt, dt__lte=to_dt))
    """
    work_day_amount -- количество рабочих дней
    holiday_amount -- количество выходных дней
    sick_day_amount -- количество больничных
    work_day_in_holidays_amount -- количество рабочих дней в праздники
    vacation_day_amount -- количество дней отпуска
    change_amount -- количество изменений в графике
    """

    work_day_amount = utils.count(days, lambda x: x.type == models.WorkerDay.Type.TYPE_WORKDAY)
    holiday_amount = utils.count(days, lambda x: x.type == models.WorkerDay.Type.TYPE_HOLIDAY)
    sick_day_amount = utils.count(days, lambda x: x.type == models.WorkerDay.Type.TYPE_SICK)
    vacation_day_amount = utils.count(days, lambda x: x.type == models.WorkerDay.Type.TYPE_VACATION)

