from src.db.models import (
    User,
    AttendanceRecords,
    # UserIdentifier,
    Shop
)
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import AttendanceRecordsConverter
from .forms import GetUserUrvForm, ChangeAttendanceForm
from django.db.models import Q
import functools
from django.core.paginator import Paginator, EmptyPage


@api_method(
    'GET',
    GetUserUrvForm,
    # check_permissions=False,
    # lambda_func=None,  # lambda x: User.objects.get(id=x['worker_ids'][0])
)
def get_user_urv(request, form):
    """

    Args:
         method: GET
         url: /urv/get_user_urv
         worker_ids(list): список айдишников юзеров, для которых выгружать
         from_dt(QOS_DATE): с какого числа выгружать данные
         to_dt(QOS_DATE): по какое
         offset(int): смещение по страницам (по дефолту первая)
         amount_per_page(int): количество результатов на страницу (по умолчанию 50)
    Returns:
        {}
    """
    worker_ids = form['worker_ids']
    from_dt = form['from_dt']
    to_dt = form['to_dt']
    offset = form['offset'] if form['offset'] else 1
    amount_per_page = form['amount_per_page'] if form['amount_per_page'] else 50

    # if not len(worker_ids):
    #     worker_ids = list(User.objects.qos_filter_active(
    #         to_dt,
    #         from_dt,
    #         shop_id=request.user.shop_id
    #     ).values_list('id', flat=True))


    user_records = AttendanceRecords.objects.filter(
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
        shop_id=form['shop_id'],
    )

    if len(worker_ids):
        user_records = user_records.filter(
            Q(user_id__in=worker_ids) |
            Q(user_id__isnull=True) |
            Q(user__attachment_group=User.GROUP_OUTSOURCE)
        )
    if form['from_tm']:
        user_records = user_records.filter(dttm__time__gte=form['from_tm'])
    if form['to_tm']:
        user_records = user_records.filter(dttm__time__lte=form['to_tm'])
    if form['type']:
        user_records = user_records.filter(type=form['type'])

    select_not_verified = False
    select_not_detected = False
    select_workers = False
    select_outstaff = False

    if form['show_not_verified']:
        select_not_verified = Q(verified=False)

    if form['show_not_detected']:
        select_not_detected = Q(user_id__isnull=True)

    if form['show_workers']:
        select_workers = Q(user__attachment_group=User.GROUP_STAFF)

    if form['show_outstaff']:
        select_outstaff = Q(user__attachment_group=User.GROUP_OUTSOURCE)

    extra_filters = list(filter(lambda x: x, [select_not_verified, select_not_detected, select_workers, select_outstaff]))
    if len(extra_filters):
        extra_filters = functools.reduce(lambda x, y: x | y, extra_filters)
        user_records = user_records.filter(extra_filters)

    user_records = user_records.order_by('-dttm')

    paginator = Paginator(user_records, amount_per_page)
    try:
        user_records = paginator.page(offset)
    except EmptyPage:
        return JsonResponse.value_error('Запрашиваемая страница не существует')
    info = {
        'offset': offset,
        'pages': paginator.count,
        'amount_per_page': amount_per_page,
    }

    return JsonResponse.success([
        AttendanceRecordsConverter.convert(record) for record in user_records
    ], info)


@api_method(
    'POST',
    ChangeAttendanceForm,
    # check_permissions=False,
    # lambda_func=None,  # lambda x: User.objects.get(id=x['worker_ids'][0])
)
def change_user_urv(request, form):
    return JsonResponse.success()
    # if not form['to_user_id'] and not form['is_outsource']:
    #     return JsonResponse.value_error('Выберите, пожалуйста, либо сотрудника, либо вариант аутсорса.')
    #
    # identifier = UserIdentifier.objects.get(attendancerecords__id=form['attendance_id'])
    #
    # if form['is_outsource']:
    #     dt = timezone.now().date()
    #     outsourcer_number = User.objects.filter(
    #         attachment_group=User.GROUP_OUTSOURCE,
    #         dt_hired=dt,
    #         dt_fired=dt,
    #     ).count()
    #     user = User.objects.create(
    #         shop_id=request.user.shop_id,
    #         attachment_group=User.GROUP_OUTSOURCE,
    #         first_name='№{}'.format(outsourcer_number + 1),
    #         last_name='Наемный сотрудник',
    #         dt_hired=dt,
    #         dt_fired=dt,
    #         salary=0,
    #         username='outsourcer_{}_{}'.format(dt, outsourcer_number + 1),
    #         auto_timetable=False
    #     )
    # else:
    #     user = User.objects.get(
    #         id=form['to_user_id'],
    #         shop_id=request.user.shop_id,
    #     )
    #
    # identifier.worker = user
    # identifier.save()
    # return JsonResponse.success()
