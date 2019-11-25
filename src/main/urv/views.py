from datetime import datetime
import functools

from django.db.models import Q
from django.core.paginator import Paginator, EmptyPage

from src.db.models import (
    AttendanceRecords,
    User,
    WorkerDay
)
from src.util.utils import JsonResponse, api_method
from src.util.models_converter import AttendanceRecordsConverter
from src.util.forms import FormUtil
from .forms import GetUserUrvForm
from .utils import wd_stat_count_total


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

    from_dt = form['from_dt']
    to_dt = form['to_dt']

    if form['from_tm']:
        from_dt = datetime.combine(from_dt, form['from_tm'])
    if form['to_tm']:
        to_dt = datetime.combine(to_dt, form['to_tm'])

    user_records = AttendanceRecords.objects.filter(
        dttm__date__gte=from_dt,
        dttm__date__lte=to_dt,
        shop_id=form['shop_id'],
    ).order_by('dttm')

    if len(form['worker_ids']):
        user_records = user_records.filter(
            Q(user_id__in=form['worker_ids']) |
            Q(user_id__isnull=True) |
            Q(user__attachment_group=User.GROUP_OUTSOURCE)
        )
    if form['type']:
        user_records = user_records.filter(type=form['type'])

    extra_filters = []
    if form['show_not_verified']:
        extra_filters.append(Q(verified=False))

    if form['show_not_detected']:
        extra_filters.append(Q(user_id__isnull=True))

    if form['show_workers']:
        extra_filters.append(Q(user__attachment_group=User.GROUP_STAFF))

    if form['show_outstaff']:
        extra_filters.append(Q(user__attachment_group=User.GROUP_OUTSOURCE))

    if len(extra_filters):
        extra_filters = functools.reduce(lambda x, y: x | y, extra_filters)
        user_records = user_records.filter(extra_filters)


    amount_per_page = form['amount_per_page'] if form['amount_per_page'] else 50
    offset = form['offset'] if form['offset'] else 1

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
         from_tm: время с
         to_tm: время по
         shop_id: id магазина
         show_outstaff
         show_workers
         show_not_verified
         show_not_detected
    """
    from_dt = form['from_dt']
    to_dt = form['to_dt']

    if form['from_tm']:
        from_dt = datetime.combine(from_dt, form['from_tm'])
    if form['to_tm']:
        to_dt = datetime.combine(to_dt, form['to_tm'])

    worker_ids = form['worker_ids']

    checkpoint = FormUtil.get_checkpoint(form)
    worker_days = WorkerDay.objects.qos_filter_version(checkpoint).filter(
        dt__gte=from_dt,
        dt__lte=to_dt,
        worker__shop_id=form['shop_id'],
        type=WorkerDay.TYPE_WORKDAY
    )
    if len(worker_ids):
        worker_days = worker_days.filter(
            worker_id__in=worker_ids,
        )

    if form['from_tm']:
        worker_days = worker_days.filter(dttm_work_start__time__gte=form['from_tm'])

    if form['to_tm']:
        worker_days = worker_days.filter(dttm_work_end__time__lte=form['to_tm'])

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

    wd_stat = wd_stat_count_total(worker_days, request.shop)
    indicators = {
        'ticks_coming_count_fact': wd_stat['ticks_coming_count'],
        'ticks_leaving_count_fact': wd_stat['ticks_leaving_count'],
        'ticks_count_fact': wd_stat['ticks_coming_count'] + wd_stat['ticks_leaving_count'],
        'hours_count_fact': wd_stat['hours_count_fact'],
        'ticks_count_plan': ticks_count_plan,
        'hours_count_plan': wd_stat['hours_count_plan'],
        'lateness_count': wd_stat['lateness_count']
    }

    return JsonResponse.success(indicators)
