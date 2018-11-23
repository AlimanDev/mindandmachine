from src.db.models import (
    User,
    AttendanceRecords,
)
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import AttendanceRecordsConverter
from .forms import GetUserUrvForm


@api_method(
    'GET',
    GetUserUrvForm,
    lambda_func=lambda x: User.objects.get(id=x['worker_ids'][0])
)
def get_user_urv(request, form):
    """

    Args:
         method: GET
         url: /urv/get_user_urv
         worker_ids(list): список айдишников юзеров, для которых выгружать
         from_dt(QOS_DATE): с какого числа выгружать данные
         to_dt(QOS_DATE): по какое
    Returns:
        {}
    """

    PER_PAGE = 20

    worker_ids = form['worker_ids']
    from_dt = form['from_dt']
    to_dt = form['to_dt']
    offset = form['offset']

    if offset is None:
        offset = 0

    if len(worker_ids):
        worker_ids = list(User.objects.qos_filter_active(
            to_dt,
            from_dt,
            shop_id=request.user.shop_id
        ).values_list('id', flat=True))

    user_records = AttendanceRecords.objects.select_related('identifier').filter(
        identifier__worker_id__in=worker_ids,
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
    ).order_by(
        '-dttm',
    )[offset * PER_PAGE: (offset + 1) * PER_PAGE]

    return JsonResponse.success([
        AttendanceRecordsConverter.convert(record) for record in user_records
    ])
