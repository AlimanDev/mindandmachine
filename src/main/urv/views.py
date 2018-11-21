import datetime

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
    lambda_func=lambda x: User.objects.get(id=x['worker_id'])
)
def get_user_urv(request, form):
    """

    Args:
         method: GET
         url: /urv/get_user_urv
         worker_id(int):
         from_dt(QOS_DATE): с какого числа выгружать данные
         to_dt(QOS_DATE): по какое
    Returns:
        {}
    """
    worker_id = form['worker_id']
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    user_records = AttendanceRecords.objects.filter(
        worker_id=worker_id,
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
    )

    return JsonResponse.success([
        AttendanceRecordsConverter.convert(record) for record in user_records
    ])
