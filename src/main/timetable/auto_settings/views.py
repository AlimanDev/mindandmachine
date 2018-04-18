from datetime import datetime

from src.db.models import Timetable, User
from src.util.forms import FormUtil
from src.util.models_converter import TimetableConverter
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
        Timetable.objects.create(
            shop_id=shop_id,
            dt=form['dt'],
            status=Timetable.Status.PROCESSING,
            dttm_status_change=datetime.now()
        )
    except:
        return JsonResponse.already_exists_error()

    return JsonResponse.success()


@api_method('POST', DeleteTimetableForm)
def delete_timetable(request, form):
    shop_id = FormUtil.get_shop_id(request, form)
    Timetable.objects.filter(shop_id=shop_id, dt=form['dt']).delete()
    return JsonResponse.success()


@api_method('POST', SetTimetableForm)
def set_timetable(request, form):
    return JsonResponse.success()
