import xlsxwriter
import datetime
import io
import calendar
from dateutil.relativedelta import relativedelta

from django.http import HttpResponse
from django.db.models.functions import Coalesce
from functools import reduce
from django.db.models import Sum, Q
from src.db.models import (
    User,
    WorkerCashboxInfo,
    WorkerDay,
    WorkerDayCashboxDetails,
    PeriodDemand,
    CashboxType,
    Shop
)
from src.util.forms import FormUtil
from src.util.models_converter import (
    UserConverter,
    BaseConverter,
    WorkerDayConverter,
)
from src.util.utils import api_method, JsonResponse
from .forms import (
    SelectCashiersForm,
    GetWorkerStatForm,
)
from src.conf.djconfig import QOS_SHORT_TIME_FORMAT
from .utils import (
    count_work_month_stats,
    count_normal_days,
)

from src.main.download.forms import GetTable
from .utils import count_difference_of_normal_days


@api_method('GET', SelectCashiersForm)
def select_cashiers(request, form):
    """
    Args:
        method: GET
        url: /api/timetable/table/select_cashiers
        cashbox_types(list): required = True
        cashier_ids(list): required = True
        work_types(str): required = False
        workday_type(str): required = False
        workdays(str): required = False
        shop_id(int): required = False
        work_workdays(str): required = False
        from_tm(QOS_TIME): required = False
        to_tm(QOS_TIME): required = False
        checkpoint(int): required = False (0 -- для начальной версии, 1 -- для текущей)

    """
    shop_id = FormUtil.get_shop_id(request, form)
    checkpoint = FormUtil.get_checkpoint(form)

    users = User.objects.filter(shop_id=shop_id, attachment_group=User.GROUP_STAFF)

    cashboxes_type_ids = set(form.get('cashbox_types', []))
    if len(cashboxes_type_ids) > 0:
        users_hits = set()
        for x in WorkerCashboxInfo.objects.select_related('cashbox_type').filter(cashbox_type__shop_id=shop_id, is_active=True):
            if x.cashbox_type_id in cashboxes_type_ids:
                users_hits.add(x.worker_id)

        users = [x for x in users if x.id in users_hits]

    cashier_ids = set(form.get('cashier_ids', []))
    if len(cashier_ids) > 0:
        users = [x for x in users if x.id in cashier_ids]

    work_types = set(form.get('work_types', []))
    if len(work_types) > 0:
        users = [x for x in users if x.work_type in work_types]

    worker_days = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(worker__shop_id=shop_id)

    workday_type = form.get('workday_type')
    if workday_type is not None:
        worker_days = worker_days.filter(type=workday_type)

    workdays = form.get('workdays')
    if len(workdays) > 0:
        worker_days = worker_days.filter(dt__in=workdays)

    users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]

    work_workdays = form.get('work_workdays', [])
    if len(work_workdays) > 0:
        def __is_match_tm(__x, __tm_from, __tm_to):
            if __x.dttm_work_start.time() < __x.dttm_work_end.time():
                if __tm_from > __x.dttm_work_end.time():
                    return False
                if __tm_to < __x.dttm_work_start.time():
                    return False
                return True
            else:
                if __tm_from >= __x.dttm_work_start.time():
                    return True
                if __tm_to <= __x.dttm_work_end.time():
                    return True
                return False

        worker_days = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
            worker__shop_id=shop_id,
            type=WorkerDay.Type.TYPE_WORKDAY.value,
            dt__in=work_workdays
        )

        tm_from = form.get('from_tm')
        tm_to = form.get('to_tm')
        if tm_from is not None and tm_to is not None:
            worker_days = [x for x in worker_days if __is_match_tm(x, tm_from, tm_to)]

        users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]

    return JsonResponse.success([UserConverter.convert(x) for x in users])


@api_method('GET', GetTable)
def get_table(request, form):
    """
    Args:
        method: GET
        url: /api/timetable/table/get_table
        shop_id(int): required = False
        weekday(QOS_DATE): required = True
    """
    font_size = 12
    boarder_size = 1
    checkpoint = FormUtil.get_checkpoint(form)

    def mix_formats(workbook, *args):
        return workbook.add_format(reduce(lambda x, y: {**x, **y} if y is not None else x, args[0:], {}))

    def write_global_header(workbook, worksheet, weekday):
        weekday_translation = [
            'Понедельник',
            'Вторник',
            'Среда',
            'Четверг',
            'Пятница',
            'Суббота',
            'Воскресенье'
        ]
        right_border = workbook.add_format({'right': 2, 'font_size': font_size})
        bold_right_border = workbook.add_format({'right': 2, 'bold': True, 'font_size': font_size})
        border = workbook.add_format({'border': 2, 'font_size': font_size})
        worksheet.write('A1', 'Дата:')
        worksheet.merge_range('B1:C1', weekday.strftime('%d/%m/%Y'), right_border)
        worksheet.write_blank(0, 4, '', right_border)
        worksheet.merge_range('F1:G1', 'День недели:')
        worksheet.merge_range('H1:K1', weekday_translation[weekday.weekday()], bold_right_border)
        worksheet.merge_range('A2:K2', '', border)

    def write_workers_header(workbook, worksheet):
        long_column_width = 24
        short_column_width = long_column_width/2
        centred_bold_border = workbook.add_format({'border': 2, 'text_wrap': True, 'bold': True, 'align': 'center', 'font_size': font_size})
        worksheet.set_row(2, 95)
        worksheet.write('A3', 'Фамилия', centred_bold_border)
        worksheet.set_column('A:A', long_column_width)
        worksheet.merge_range('B3:C3', 'Специализация', centred_bold_border)
        worksheet.set_column('B:C', short_column_width)
        worksheet.write('D3', 'Время прихода', centred_bold_border)
        worksheet.write_blank('E3', '', centred_bold_border)
        worksheet.write('F3', 'Время ухода', centred_bold_border)
        worksheet.write_blank('G3', '', centred_bold_border)
        worksheet.set_column('D:G', short_column_width)
        worksheet.merge_range('H3:K3', 'Перерывы', centred_bold_border)
        worksheet.set_column('H:K', short_column_width/2)
        worksheet.set_column('N:N', short_column_width)  # should in next func
        worksheet.set_column('O:Q', short_column_width/4)  # should in next func

    def write_stats_header(workbook, worksheet):
        border = workbook.add_format({'border': boarder_size, 'font_size': font_size})
        border_vertical = workbook.add_format({'border': boarder_size, 'font_size': font_size, 'rotation': 90})
        worksheet.write('N3', 'Время', border)
        worksheet.write('O3', 'Факт', border_vertical)
        worksheet.write('P3', 'Должно быть', border_vertical)
        worksheet.write('Q3', 'Разница', border_vertical)

    def create_stats_dictionary(tm_st, tm_end):
        stats = {}
        tm = datetime.datetime.combine(
            datetime.date.today(),
            tm_st,
        )
        tm_step = datetime.timedelta(
            minutes=30
        )
        tm_end = datetime.datetime.combine(
            datetime.date.today(),
            tm_end,
        )
        before_start = datetime.time(hour=6, minute=45)
        stats[before_start] = []
        while tm < tm_end:
            stats[tm.time()] = []
            tm += tm_step

        return stats

    def write_workers(workbook, worksheet, shop_id, stats, weekday):
        bold_right_cell_format = {'right': boarder_size, 'top': boarder_size, 'bottom': boarder_size}
        bold_left_cell_format = {'left': boarder_size,  'top': boarder_size, 'bottom': boarder_size}
        bold_format = {'bold': True}
        size_format = {'font_size': font_size}
        align_right = {'align': 'right'}

        # TODO: move status updation to other function
        local_stats = dict(stats)
        row = 3
        start_row = row
        workerdays = WorkerDay.objects.qos_filter_version(checkpoint).select_related('worker').filter(
            worker__shop__id=shop_id,
            worker__shop__title="Кассиры",
            dt=weekday,
        ).order_by(
            'dttm_work_start',
            'worker__last_name'
        )

        for workerday in workerdays:
            day_detail = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).select_related(
                    'cashbox_type'
                ).filter(
                    worker_day=workerday
                ).first()

            is_working_or_main_type = False
            if day_detail is None or (day_detail.cashbox_type and not day_detail.cashbox_type.is_main_type):
                is_working_or_main_type = True

            bg_color_format = {'bg_color': '#D9D9D9'} if is_working_or_main_type else None
            to_align_right = align_right if is_working_or_main_type else None
            if workerday.dttm_work_start is None\
                or workerday.dttm_work_end is None\
                or workerday.type != WorkerDay.Type.TYPE_WORKDAY.value:
                continue
            # user data
            worksheet.write(
                row,
                0,
                '{} {}'.format(workerday.worker.last_name, workerday.worker.first_name),
                mix_formats(
                    workbook,
                    bold_left_cell_format,
                    bold_format,
                    bg_color_format,
                    to_align_right,
                    size_format
                )
            )
            # specialization
            try:
                workerday_cashbox_details_first = day_detail
                if workerday_cashbox_details_first is None:
                    worksheet.write_blank(row, 1, '', mix_formats(workbook, bold_left_cell_format, bold_format, bg_color_format, size_format))
                    worksheet.write_blank(row, 2, '', mix_formats(workbook, bold_right_cell_format, bold_format, bg_color_format, size_format))
                    raise WorkerDayCashboxDetails.DoesNotExist

                if workerday_cashbox_details_first.cashbox_type:
                    worksheet.write(row, 1, workerday_cashbox_details_first.cashbox_type.name, mix_formats(workbook, bold_left_cell_format, bold_format, bg_color_format, size_format))
                worksheet.write_blank(row, 2, '', mix_formats(workbook, bold_right_cell_format, bg_color_format, size_format))
            except WorkerDayCashboxDetails.DoesNotExist:
                pass
            # rest time
            rest_time = ['', '0:15', '0:15', '0:45']
            worksheet.write_row(row, 7, rest_time, mix_formats(workbook, bold_right_cell_format, bold_format, bg_color_format, size_format))
            worksheet.write_blank(row, 7+len(rest_time), '',
                mix_formats(workbook, size_format))
            # start and end time
            worksheet.write(row, 3, workerday.dttm_work_start.time().strftime(QOS_SHORT_TIME_FORMAT),
                mix_formats(workbook, bold_left_cell_format, bold_format, bg_color_format, size_format))
            worksheet.write_blank(row, 4, '',
                mix_formats(workbook, bold_left_cell_format, bold_format, bg_color_format, size_format))
            worksheet.write(row, 5, workerday.dttm_work_end.time().strftime(QOS_SHORT_TIME_FORMAT),
                mix_formats(workbook, bold_left_cell_format, bold_format, bg_color_format, size_format))
            worksheet.write_blank(row, 6, '',
                mix_formats(workbook, bold_left_cell_format, bold_right_cell_format, bold_format, bg_color_format, size_format))
            # update stats
            for stat_time in local_stats:
                if stat_time >= workerday.dttm_work_start.time() and \
                        (stat_time < workerday.dttm_work_end.time() or workerday.dttm_work_end.time().hour == 0):
                    local_stats[stat_time].append(workerday)
            row += 1

        return local_stats, row

    def write_stats(workbook, worksheet, stats, weekday, shop_id):
        tm_st_ad2 = datetime.time(8, 30)
        tm_st_ad4 = datetime.time(10)
        tm_end_ad4 = datetime.time(21)
        tm_end_ad2 = datetime.time(22, 30)

        border = {'border': boarder_size}
        size_format = {'font_size': font_size}
        # write stats
        row = 3
        col = 13
        predictions = PeriodDemand.objects.filter(
            dttm_forecast__range=(
                datetime.datetime.combine(weekday, datetime.time()),
                datetime.datetime.combine(weekday, datetime.time(hour=23, minute=59))
            ),
            cashbox_type__shop_id=shop_id,
            cashbox_type__do_forecast=CashboxType.FORECAST_HARD,
        )

        inds = list(stats)
        inds.sort()

        ct_add = CashboxType.objects.filter(shop_id=shop_id, do_forecast=CashboxType.FORECAST_LITE).count()

        for tm in inds:
            worksheet.write(row, col, tm.strftime(QOS_SHORT_TIME_FORMAT), mix_formats(workbook, border, size_format))
            # in facts workers
            in_fact = len(stats[tm])
            worksheet.write(row, col+1, in_fact, mix_formats(workbook, border, size_format))
            # predicted workers
            predicted = list(filter(
                lambda prediction: prediction.dttm_forecast == datetime.datetime.combine(weekday, tm),
                predictions
            ))
            result_prediction = 0
            for prediction in predicted:
                if prediction.cashbox_type.is_main_type:
                    result_prediction += prediction.clients / 14
                else:
                    result_prediction += prediction.clients / 4
            if tm_st_ad4 < tm < tm_end_ad4:
                result_prediction += 4
            elif tm_st_ad2 < tm < tm_end_ad2:
                result_prediction += 2
            result_prediction += ct_add
            result_prediction = int(result_prediction + 0.5)
            worksheet.write(row, col+2, result_prediction, mix_formats(workbook, border, size_format))
            worksheet.write(row, col+3, in_fact - result_prediction, mix_formats(workbook, border, size_format))
            row += 1

        return row

    def write_stats_summary(workbook, worksheet, stats, last_row):
        border_format = {'border': boarder_size}
        centered_format = {'align': 'center'}
        size_format = {'font_size': font_size}
        row = last_row
        col = 13

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'утро 08:00', mix_formats(workbook, border_format, centered_format, size_format))
        worksheet.write(row, col+3, len(stats[datetime.time(hour=8)]), mix_formats(workbook, border_format, centered_format, size_format))

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'утро 8:00 - 9:30', mix_formats(workbook, border_format, centered_format, size_format))
        worksheet.write(row, col+3, len(stats[datetime.time(hour=9, minute=30)]), mix_formats(workbook, border_format, centered_format, size_format))

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'утро 8:00 - 12:30', mix_formats(workbook, border_format, centered_format, size_format))
        worksheet.write(row, col+3, len(stats[datetime.time(hour=12, minute=30)]), mix_formats(workbook, border_format, centered_format, size_format))

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'вечер', mix_formats(workbook, border_format, centered_format, size_format))
        worksheet.write(row, col+3, len(stats[datetime.time(hour=21)]), mix_formats(workbook, border_format, centered_format, size_format))

        return row

    def write_overtime(workbook, worksheet, last_row):
        size_format = {'font_size': font_size}
        bg_color_format = {'bg_color': '#D9D9D9'}
        border = {'border': boarder_size}
        row = last_row + 4
        worksheet.write(row, 0, 'Подработка, выход в выходной', mix_formats(workbook, size_format, bg_color_format))
        for col in range(1, 11):
            worksheet.write_blank(row, col, '', mix_formats(workbook, size_format, bg_color_format))
        row += 1
        for i in range(5):
            for col in range(11):
                worksheet.write_blank(row + i, col, '', mix_formats(workbook, size_format, border))

    output = io.BytesIO()
    shop_id = FormUtil.get_shop_id(request, form)
    weekday = form['weekday']

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    # workbook = xlsxwriter.Workbook('hello.xlsx')
    worksheet = workbook.add_worksheet()
    # worksheet.set_column(0, 0, 23)
    # worksheet.set_column(1, 1, 15)
    worksheet.set_column(11, 11, 1)
    worksheet.set_column(12, 12, 1)

    write_global_header(workbook, worksheet, weekday)
    write_workers_header(workbook, worksheet)
    write_stats_header(workbook, worksheet)

    stats = create_stats_dictionary(
        datetime.time(7),
        datetime.time(23, 59, 59),
    )
    stats, last_users_row = write_workers(workbook, worksheet, shop_id, stats, weekday)
    write_overtime(workbook, worksheet, last_users_row)
    last_stats_row = write_stats(workbook, worksheet, stats, weekday, shop_id)
    write_stats_summary(workbook, worksheet, stats, last_stats_row)

    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Tablet_{}.xlsx"'.format(BaseConverter.convert_date(weekday))

    return response


@api_method('GET', GetWorkerStatForm)
def get_month_stat(request, form):
    """
    Считает статистику за месяц dt

    Args:
        method: GET
        url: /api/timetable/table/get_month_stat
        shop_id(int): required = False
        dt(QOS_DATE): required = True
        worker_ids(list): required = False
    """
    # prepare data
    dt_start = datetime.date(form['dt'].year, form['dt'].month, 1)
    dt_start_year = datetime.date(dt_start.year, 1, 1)
    dt_end = dt_start + relativedelta(months=+1)
    usrs = User.objects.qos_filter_active(dt_start, dt_end)
    # todo: add code for permissions check (check stat of workers from another shops)
    worker_ids = form['worker_ids']

    if (worker_ids is None) or (len(worker_ids) == 0):
        shop_id = FormUtil.get_shop_id(request, form)

        usrs = usrs.filter(shop_id=shop_id)
    else:
        usrs = usrs.filter(id__in=worker_ids)
    usrs = usrs.order_by('id')

    # count info of current month
    month_info = count_work_month_stats(dt_start, dt_end, usrs)

    user_info_dict = count_difference_of_normal_days(dt_end=dt_start, usrs=usrs)

    for u_it in range(len(usrs)):
        month_info[usrs[u_it].id].update({
            'diff_prev_paid_days': user_info_dict[usrs[u_it].id]['diff_prev_paid_days'],
            'diff_prev_paid_hours': user_info_dict[usrs[u_it].id]['diff_prev_paid_hours'],
            'diff_total_paid_days': user_info_dict[usrs[u_it].id]['diff_prev_paid_days'] + month_info[usrs[u_it].id]['diff_norm_days'],
            'diff_total_paid_hours': user_info_dict[usrs[u_it].id]['diff_prev_paid_hours'] + month_info[usrs[u_it].id]['diff_norm_hours'],
        })
    return JsonResponse.success({'users_info': month_info})




