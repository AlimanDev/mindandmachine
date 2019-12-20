import xlsxwriter
import datetime
import io
from dateutil.relativedelta import relativedelta

from django.http import HttpResponse
from functools import reduce
from src.db.models import (
    Employment,
    OperationType,
    PeriodClients,
    User,
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
    Shop
)
from src.util.forms import FormUtil
from src.util.models_converter import (
    Converter,
)
from src.util.utils import api_method, JsonResponse
from .forms import GetWorkerStatForm, WorkersToExchange
from src.conf.djconfig import QOS_SHORT_TIME_FORMAT
from .utils import (
    count_work_month_stats,
)

from src.main.download.forms import GetTable
from src.main.download.utils import xlsx_method
from .utils import count_difference_of_normal_days


@api_method('GET', GetTable)
@xlsx_method
def get_table(request, workbook, form):
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
            shop__id=shop_id,
            # shop__title="Кассиры",
            dt=weekday,
        ).order_by(
            'dttm_work_start',
            'worker__last_name'
        )

        for workerday in workerdays:
            day_detail = WorkerDayCashboxDetails.objects.qos_filter_version(checkpoint).select_related(
                    'work_type'
                ).filter(
                    worker_day=workerday
                ).first()

            is_working_or_main_type = False
            if day_detail is None or day_detail.work_type:
                is_working_or_main_type = True

            bg_color_format = {'bg_color': '#D9D9D9'} if is_working_or_main_type else None
            to_align_right = align_right if is_working_or_main_type else None
            if workerday.dttm_work_start is None\
                or workerday.dttm_work_end is None\
                or workerday.type != WorkerDay.TYPE_WORKDAY:
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

                if workerday_cashbox_details_first.work_type:
                    worksheet.write(row, 1, workerday_cashbox_details_first.work_type.name, mix_formats(workbook, bold_left_cell_format, bold_format, bg_color_format, size_format))
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
        predictions = PeriodClients.objects.filter(
            dttm_forecast__range=(
                datetime.datetime.combine(weekday, datetime.time()),
                datetime.datetime.combine(weekday, datetime.time(hour=23, minute=59))
            ),
            operation_type__work_type__shop_id=shop_id,
            operation_type__do_forecast=OperationType.FORECAST_HARD,
        )

        inds = list(stats)
        inds.sort()

        ct_add = WorkType.objects.filter(
            shop_id=shop_id,
            work_type_reversed__do_forecast=OperationType.FORECAST_LITE
        ).count()

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
                # if prediction.work_type.is_main_type:
                #     result_prediction += prediction.value / 14
                # else:
                    result_prediction += prediction.value / 4
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
    shop_id = form['shop_id']
    weekday = form['weekday']

    #workbook = xlsxwriter.Workbook(output, {'in_memory': True})
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
    '''
    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Tablet_{}.xlsx"'.format(Converter.convert_date(weekday))
    
    return response
    '''
    return workbook, f'Tablet_{Converter.convert_date(weekday)}.xlsx'


@api_method('GET', GetWorkerStatForm)
def get_month_stat(request, form):
    """
    Считает статистику за месяц dt

    Args:
        method: GET
        url: /api/timetable/table/get_month_stat
        shop_id(int): required = True
        dt(QOS_DATE): required = True
        worker_ids(list): required = False
    """
    # prepare data
    dt_start = datetime.date(form['dt'].year, form['dt'].month, 1)
    dt_end = dt_start + relativedelta(months=+1) - datetime.timedelta(days=1)
    shop = request.shop
    employments = Employment.objects.get_active(
        dt_start, dt_end,
        shop_id=shop.id
    ).select_related('user').order_by('id')

    # todo: add code for permissions check (check stat of workers from another shops)
    worker_ids = form['worker_ids']
    if worker_ids and len(worker_ids):
        employments=employments.filter(user_id__in=worker_ids)

    # count info of current month
    month_info = count_work_month_stats(shop, dt_start, dt_end, employments)

    stat_prev_month = count_difference_of_normal_days(dt_end=dt_start, employments=employments, shop=shop)

    for employment in employments:
        if employment.user_id not in month_info:
            continue
        emp_prev_stat = stat_prev_month[employment.id]
        emp_month_info = month_info[employment.user_id]

        emp_month_info.update({
            'diff_prev_paid_days': emp_prev_stat['diff_prev_paid_days'],
            'diff_prev_paid_hours': emp_prev_stat['diff_prev_paid_hours'],
            'diff_total_paid_days': emp_prev_stat['diff_prev_paid_days'] + emp_month_info['diff_norm_days'],
            'diff_total_paid_hours': emp_prev_stat['diff_prev_paid_hours'] + emp_month_info['diff_norm_hours'],
        })
    return JsonResponse.success({'users_info': month_info})


@api_method(
    'POST',
    WorkersToExchange,
)
def exchange_workers_day(request, form):
    """
    Обмен рабочим расписанием между двумя сотрудниками в заданный день
    Args:
         method: POST
         url: /api/timetable/table/exchange_workers_day
         worker1_id(int): id первого пользователя
         worker2_id(int): id второго пользователя
         from_dt(QOS_DATE): дата для замены, c которой обменять график сотрудников
         to_dt(QOS_DATE): дата для замены, по которую включительно обменять график сотрудников
         shop_id: required = True
    Returns:
        {}
    """

    def create_worker_day(wd_parent, wd_swap):
        wd_new = WorkerDay(
            type=wd_swap.type,
            dttm_work_start=wd_swap.dttm_work_start,
            dttm_work_end=wd_swap.dttm_work_end,
            worker_id=wd_parent.worker_id,
            dt=wd_parent.dt,
            parent_worker_day=wd_parent,
            created_by=request.user,
        )
        wd_new.save()

        wd_cashbox_details_new = []
        for wd_cashbox_details_parent in wd_swap.workerdaycashboxdetails_set.all():
            wd_cashbox_details_new.append(WorkerDayCashboxDetails(
                worker_day_id=wd_new.id,
                on_cashbox_id=wd_cashbox_details_parent.on_cashbox_id,
                work_type_id=wd_cashbox_details_parent.work_type_id,
                status=wd_cashbox_details_parent.status,
                is_tablet=wd_cashbox_details_parent.is_tablet,
                dttm_from=wd_cashbox_details_parent.dttm_from,
                dttm_to=wd_cashbox_details_parent.dttm_to,
            ))
        WorkerDayCashboxDetails.objects.bulk_create(wd_cashbox_details_new)

    if form['to_dt'] < form['from_dt']:
        return JsonResponse.value_error('Первая дата должна быть меньше второй')

    days = (form['to_dt'] - form['from_dt']).days + 1

    wd_parent_list = list(WorkerDay.objects.qos_current_version().filter(
        worker_id__in=(form['worker1_id'], form['worker2_id']),
        dt__gte=form['from_dt'],
        dt__lte=form['to_dt'],
    ).order_by('dt'))

    if len(wd_parent_list) != days * 2:
        return JsonResponse.value_error('Отсутствует расписание сотрудников')

    day_pairs = []
    for day_ind in range(days):
        day_pair = [wd_parent_list[day_ind * 2], wd_parent_list[day_ind * 2 + 1]]
        if day_pair[0].dt != day_pair[1].dt:
            return JsonResponse.value_error('Отсутствует расписание сотрудников')
        day_pairs.append(day_pair)

    for day_pair in day_pairs:
        create_worker_day(day_pair[0], day_pair[1])
        create_worker_day(day_pair[1], day_pair[0])

    return JsonResponse.success()
