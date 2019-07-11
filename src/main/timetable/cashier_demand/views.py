from datetime import datetime, timedelta, date

from django.http import HttpResponse
from django.db.models import Q
from src.main.timetable.cashier_demand.utils import get_worker_timetable2 as get_worker_timetable
from src.main.download.xlsx.timetable import download

from src.db.models import (
    WorkerDay,
    User,
    WorkerDayCashboxDetails,
)
from src.main.timetable.cashier_demand.forms import GetWorkersForm, GetCashiersTimetableForm
from src.util.models_converter import UserConverter, BaseConverter
from src.util.utils import api_method, JsonResponse
from src.util.forms import FormUtil
from src.conf.djconfig import QOS_DATETIME_FORMAT

from dateutil.relativedelta import relativedelta

import xlsxwriter
import io


@api_method('GET', GetWorkersForm)
def get_workers(request, form):
    """
    Todo: сделать нормальное описание

    Args:
        method: GET
        url: /api/timetable/cashier_demand/get_workers
        from_dttm(QOS_DATETIME): required = True
        to_dttm(QOS_DATETIME): required = True
        work_type_ids(list): required = True ([] -- если для всех)
        shop_id(int): required = True
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    """

    checkpoint = FormUtil.get_checkpoint(form)
    from_dttm = form['from_dttm']
    to_dttm = form['to_dttm']
    shop = FormUtil.get_shop_id(request, form)

    response = {}

    worker_day_cashbox_detail = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).select_related(
        'worker_day'
    ).filter(
        Q(worker_day__worker__dt_fired__gt=from_dttm.date()) | Q(worker_day__worker__dt_fired__isnull=True),
        Q(worker_day__worker__dt_hired__lt=to_dttm.date()) | Q(worker_day__worker__dt_fired__isnull=True),
        worker_day__worker__shop_id=shop,
        worker_day__type=WorkerDay.Type.TYPE_WORKDAY.value,
        worker_day__dt=from_dttm.date(),
        worker_day__dttm_work_start__lte=from_dttm,
        worker_day__dttm_work_end__gte=to_dttm,
        status__in=[
            WorkerDayCashboxDetails.TYPE_WORK,
            WorkerDayCashboxDetails.TYPE_BREAK,
            WorkerDayCashboxDetails.TYPE_T
        ]
    )

    work_type_ids = form['work_type_ids']
    if len(work_type_ids) > 0:
        worker_day_cashbox_detail = [x for x in worker_day_cashbox_detail if x.work_type_id in work_type_ids]

    for x in worker_day_cashbox_detail:
        response[x.worker_day.worker_id] = {
            'id': x.id,
            'from_dttm': BaseConverter.convert_datetime(x.dttm_from),
            'to_dttm': BaseConverter.convert_datetime(x.dttm_to),
            'on_cashbox': x.on_cashbox_id,
            'work_type': x.work_type_id,
            'status': x.status,
            'user_info': UserConverter.convert(x.worker_day.worker)
        }

    return JsonResponse.success(response)


@api_method('GET', GetCashiersTimetableForm)
def get_timetable_xlsx(request, form):
    """
    Вьюха для скачивания расписания

    Args:
        method: GET
        url: /api/timetable/cashier_demand/get_timetable_xlsx
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        work_type_ids(list): required = True (либо [] -- если для всех типов касс)
        format(str): 'raw' или 'excel'. default = 'raw'
        position_id(int): required = False
        shop_id(int): required = False
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        Файл расписания
    """
    shop = FormUtil.get_shop_id(request, form)
    dt_from = datetime(year=form['from_dt'].year, month=form['from_dt'].month, day=1)
    dt_to = dt_from + relativedelta(months=1) - timedelta(days=1)
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet()
    checkpoint = FormUtil.get_checkpoint(form)

    row = 6
    col = 5
    for user in User.objects.qos_filter_active(dt_from, dt_to, shop=shop).order_by('id'):
        worksheet.write(row, 0, "{} {} {}".format(user.last_name, user.first_name, user.middle_name))
        for i in range(dt_to.day):
            worksheet.write(row, col + 3 * i + 0, 'НД')
            worksheet.write(row, col + 3 * i + 1, 'НД')

        for wd in WorkerDay.objects.qos_filter_version(checkpoint).filter(worker=user, dt__gte=dt_from,
                                                                          dt__lte=dt_to).order_by('dt'):
            if wd.type == WorkerDay.Type.TYPE_HOLIDAY.value:
                cell_1 = 'В'
                cell_2 = 'В'
            elif wd.type == WorkerDay.Type.TYPE_VACATION.value:
                cell_1 = 'ОТ'
                cell_2 = 'ОТ'
            else:
                cell_1 = ''
                cell_2 = ''

            worksheet.write_string(row, col + 3 * int(wd.dt.day) - 3, cell_1)
            worksheet.write_string(row, col + 3 * int(wd.dt.day) - 2, cell_2)

        for wd in WorkerDayCashboxDetails.objects.select_related('work_type', 'worker_day').filter(
                worker_day__worker=user,
                worker_day__dt__gte=dt_from,
                worker_day__dt__lte=dt_to
        ).order_by('worker_day__dt'):
            cell_1 = wd.worker_day.dttm_work_start.strftime(QOS_DATETIME_FORMAT)
            cell_2 = wd.worker_day.dttm_work_end.strftime(QOS_DATETIME_FORMAT)
            cell_3 = wd.work_type.name

            worksheet.write_string(row, col + 3 * int(wd.worker_day.dt.day) - 3, cell_1)
            worksheet.write_string(row, col + 3 * int(wd.worker_day.dt.day) - 2, cell_2)
            worksheet.write_string(row, col + 3 * int(wd.worker_day.dt.day) - 1, cell_3)
        row += 1

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Timetable_{}.xlsx"'.format(
        BaseConverter.convert_date(dt_from))

    return response


@api_method('GET', GetCashiersTimetableForm)
def get_cashiers_timetable(request, form):
    """
    Отображает информацию о расписании кассиров на weekday на типах касс с id'шинками \
    work_types_ids

    Args:
        method: GET
        url: /api/download/get_cashiers_timetable
        from_dt(QOS_DATE): required = True
        to_dt(QOS_DATE): required = True
        work_type_ids(list): required = True (либо [] -- если для всех типов касс)
        format(str): 'raw' или 'excel'. default = 'raw'
        position_id(int): required = False
        shop_id(int): required = False
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    Returns:
        {
            'indicators': {
                | 'FOT': None,
                | 'big_demand_persent': int,
                | 'cashier_amount': int,
                | 'change_amounut'(int): количество изменений в графике,
                | 'deadtime_part'(float): доля простоя,
                | 'need_cashier_amount'(int): сколько еще нужно кассиров в этот период
            },\n
            'period_step'(int): 30,\n
            'tt_periods': {
                'fact_cashier_need': [сколько по факту нужно в период],
                'predict_cashier_needs': [сколько нужно кассиров в период],
                'real_cashiers': [сколько сидит кассиров в период]
            },\n
            'lack_of_cashiers_on_period': {
                work_type_id(int): [
                    {
                        | 'dttm_start'(QOS_DATETIME): ,
                        | 'lack_of_cashiers'(float): ,
                    },...
                ],..
            }
        }
    """
    if form['format'] == 'excel':
        return download(request, form)
    shop_id = FormUtil.get_shop_id(request, form)
    res = get_worker_timetable(shop_id, form)
    if type(res) == dict:
        res = JsonResponse.success(res)
    else:
        res = JsonResponse.value_error(res)
    return res
