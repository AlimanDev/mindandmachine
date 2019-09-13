from datetime import timedelta
import functools

from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage

from src.db.models import (
    User,
    AttendanceRecords,
    # UserIdentifier,
    Shop,
    WorkerDay
)
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import AttendanceRecordsConverter
from src.util.forms import FormUtil
from .forms import GetUserUrvForm, ChangeAttendanceForm
from .utils import get_queryset, working_hours_count


@api_method('GET', GetUserUrvForm)
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

    amount_per_page = form['amount_per_page'] if form['amount_per_page'] else 50
    offset = form['offset'] if form['offset'] else 1

    user_records = get_queryset(request, form)
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


@api_method('GET', GetUserUrvForm)
def get_indicators(request, form):
    """

    Args:
         method: GET
         url: /urv/get_indicators
         worker_ids(list): список айдишников юзеров, для которых выгружать
         from_dt(QOS_DATE): с какого числа выгружать данные
         to_dt(QOS_DATE): по какое
         offset(int): смещение по страницам (по дефолту первая)
         amount_per_page(int): количество результатов на с траницу (по умолчанию 50)
         from_tm: время с
         to_tm: время по
         shop_id: id магазина
         show_outstaff
         show_workers
         show_not_verified
         show_not_detected
    """
    ticks = get_queryset(request, form)
    from_dt = form['from_dt']
    to_dt = form['to_dt']
    worker_ids = form['worker_ids']

    checkpoint = FormUtil.get_checkpoint(form)
    worker_days = WorkerDay.objects.qos_filter_version(checkpoint).filter(
        dt__gte=from_dt,
        dt__lte=to_dt,
        worker__shop_id=form['shop_id'],
        type=WorkerDay.Type.TYPE_WORKDAY.value
    )
    if len(worker_ids):
        worker_days = worker_days.filter(
            worker_id__in=worker_ids,
        )
    if form['from_tm']:
        worker_days = worker_days.filter(dttm_work_start__time__gte=form['from_tm'])
    if form['to_tm']:
        worker_days = worker_days.filter(dttm_work_end__time__lte=form['to_tm'])

    select_not_verified = False
    select_not_detected = False
    select_workers = False
    select_outstaff = False

    if form['show_workers']:
        select_workers = Q(worker__attachment_group=User.GROUP_STAFF)

    if form['show_outstaff']:
        select_outstaff = Q(worker__attachment_group=User.GROUP_OUTSOURCE)

    extra_filters = list(filter(lambda x: x, [select_workers, select_outstaff]))
    if len(extra_filters):
        extra_filters = functools.reduce(lambda x, y: x | y, extra_filters)
        worker_days = worker_days.filter(extra_filters)


    ticks_count_plan = worker_days.count()
    if not form['type']:
        ticks_count_plan *= 2

    hours_count_plan = timedelta(hours=0)
    for wd in worker_days:
        if wd.dttm_work_end and wd.dttm_work_start:
            hours_count_plan += wd.dttm_work_end - wd.dttm_work_start

    indicators = {
        'ticks_count_fact': ticks.count(),
        'ticks_count_plan': ticks_count_plan,
        'hours_count_plan': hours_count_plan.total_seconds() / 3600,
        'hours_count_fact': working_hours_count(ticks)
    }

    return JsonResponse.success(indicators)

