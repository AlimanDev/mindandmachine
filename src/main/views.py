from . import utils
from src.db import models


def timetable_cashier_get_cashiers_set(request):
    shop_id, error_resp = utils.get_param_or_error_response(request.GET, 'shop_id', int)
    if error_resp is not None:
        return error_resp

    response_data = []
    for w in models.Worker.objects.filter(shop_id=shop_id, is_deleted=False):
        response_data.append({
            'user_id': w.id,
            'first_name': w.first_name,
            'last_name': w.last_name,
            'avatar_url': w.avatar.url
        })
    return utils.JsonResponse.success(response_data)


def timetable_cashier_get_cashier_timetable(request):
    user = models.Worker.objects.get(id=request.GET['user_id'])
    from_dt = utils.parse_date(request.GET['from_dt'])
    to_dt = utils.parse_date(request.GET['to_dt'])
    to_file_format = request.GET['to_file_format']



