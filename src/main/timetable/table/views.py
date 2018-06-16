import xlsxwriter
import datetime
import io

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
)
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
from src.conf.djconfig import SHORT_TIME_FORMAT
from .utils import (
    count_work_month_stats,
    count_normal_days,
)

from src.main.download.forms import GetTable


@api_method('GET', SelectCashiersForm)
def select_cashiers(request, form):
    shop_id = request.user.shop_id

    users = User.objects.filter(shop_id=shop_id)

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

    worker_days = WorkerDay.objects.filter(worker_shop_id=shop_id)

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
            if __x.tm_work_start < __x.tm_work_end:
                if __tm_from > __x.tm_work_end:
                    return False
                if __tm_to < __x.tm_work_start:
                    return False
                return True
            else:
                if __tm_from >= __x.tm_work_start:
                    return True
                if __tm_to <= __x.tm_work_end:
                    return True
                return False

        worker_days = WorkerDay.objects.filter(worker_shop_id=shop_id, type=WorkerDay.Type.TYPE_WORKDAY.value, dt__in=work_workdays)

        tm_from = form.get('from_tm')
        tm_to = form.get('to_tm')
        if tm_from is not None and tm_to is not None:
            worker_days = [x for x in worker_days if __is_match_tm(x, tm_from, tm_to)]

        users = [x for x in users if x.id in set(y.worker_id for y in worker_days)]

    return JsonResponse.success([UserConverter.convert(x) for x in users])


def get_table(request):
    def mix_formats(workbook, *args):
        return workbook.add_format(reduce(lambda x, y: {**x, **y} if y is not None else x, args[1:], {}))

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
        right_border = workbook.add_format({'right': 2})
        bold_right_border = workbook.add_format({'right': 2, 'bold': True})
        border = workbook.add_format({'border': 2})
        worksheet.write('A1', 'Дата:')
        worksheet.merge_range('B1:C1', weekday.strftime('%d/%m/%Y'), right_border)
        worksheet.write_blank(0, 4, '', right_border)
        worksheet.merge_range('F1:G1', 'День недели:')
        worksheet.merge_range('H1:K1', weekday_translation[weekday.weekday()], bold_right_border)
        worksheet.merge_range('A2:K2', '', border)

    def write_workers_header(workbook, worksheet):
        width_step = 8.43 * 0.8
        centred_bold_border = workbook.add_format({'border': 2, 'text_wrap': True, 'bold': True, 'align': 'center'})
        worksheet.write('A3', 'Фамилия', centred_bold_border)
        worksheet.set_column('A:A', 145 / width_step)
        worksheet.merge_range('B3:C3', 'Специализация', centred_bold_border)
        worksheet.write('D3', 'Время прихода', centred_bold_border)
        worksheet.write_blank('E3', '', centred_bold_border)
        worksheet.write('F3', 'Время ухода', centred_bold_border)
        worksheet.write_blank('G3', '', centred_bold_border)
        worksheet.merge_range('H3:K3', 'Перерывы', centred_bold_border)
        worksheet.set_column('H:K', 45 / width_step)

        worksheet.set_column('N:Q', 45 / width_step)

    def write_stats_header(workbook, worksheet):
        border = workbook.add_format({'border': 1})
        worksheet.write('N3', 'Время', border)
        worksheet.write('O3', 'Факт', border)
        worksheet.write('P3', 'Должно быть', border)
        worksheet.write('Q3', 'Разница', border)

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
        bold_right_cell_format = {'right': 2}
        bold_left_cell_format = {'left': 2}
        cell_format = {'left': 1, 'bottom': 1, 'right': 1}
        bold_format = {'bold': True}

        # TODO: move status updation to other function
        local_stats = dict(stats)
        row = 3
        start_row = row
        workerdays = WorkerDay.objects.select_related('worker').filter(
            worker__shop__id=shop_id,
            worker__shop__title="Кассиры",
            dt=weekday,
        ).order_by(
            'tm_work_start',
            'worker__last_name'
        )

        for workerday in workerdays:
            bg_color_format = {'bg_color': 'gray'} if (row - start_row) % 5 == 0 else None
            if workerday.tm_work_start is None\
                or workerday.tm_work_end is None:
                continue
            # user data
            worksheet.write(
                row,
                0,
                '{} {}'.format(workerday.worker.last_name, workerday.worker.first_name),
                mix_formats(
                    workbook,
                    cell_format,
                    bold_left_cell_format,
                    bold_format,
                    bg_color_format
                )
            )
            # specialization
            try:
                workerday_cashbox_details = WorkerDayCashboxDetails.objects.select_related(
                    'cashbox_type'
                ).filter(
                    worker_day=workerday
                ).first()
                if workerday_cashbox_details is None:
                    raise WorkerDayCashboxDetails.DoesNotExist

                worksheet.write(row, 1, workerday_cashbox_details.cashbox_type.name,
                    mix_formats(workbook, cell_format, bold_left_cell_format, bold_format, bg_color_format))
                worksheet.write_blank(row, 2, '', mix_formats(workbook, cell_format, bold_right_cell_format, bold_format, bg_color_format))
            except WorkerDayCashboxDetails.DoesNotExist:
                pass
            # rest time
            rest_time = ['', '0:15', '0:15', '0:45']
            worksheet.write_row(row, 7, rest_time, mix_formats(workbook, cell_format, bg_color_format))
            worksheet.write_blank(row, 7+len(rest_time), '',
                mix_formats(workbook, cell_format, bold_left_cell_format))
            # start and end time
            worksheet.write(row, 3, workerday.tm_work_start.strftime(SHORT_TIME_FORMAT),
                mix_formats(workbook, cell_format, bold_left_cell_format, bold_format, bg_color_format))
            worksheet.write_blank(row, 4, '',
                mix_formats(workbook, cell_format, bold_left_cell_format, bg_color_format))
            worksheet.write(row, 5, workerday.tm_work_end.strftime(SHORT_TIME_FORMAT),
                mix_formats(workbook, cell_format, bold_left_cell_format, bold_format, bg_color_format))
            worksheet.write_blank(row, 6, '',
                mix_formats(workbook, cell_format, bold_left_cell_format, bold_right_cell_format, bg_color_format))
            # update stats
            for stat_time in local_stats:
                if stat_time >= workerday.tm_work_start and (\
                    stat_time < workerday.tm_work_end or\
                    workerday.tm_work_end.hour == 0):
                    local_stats[stat_time].append(workerday)
            row += 1

        return local_stats, row

    def write_stats(workbook, worksheet, stats, weekday, shop_id):
        tm_st_ad2 = datetime.time(8, 30)
        tm_st_ad4 = datetime.time(10)
        tm_end_ad4 = datetime.time(21)
        tm_end_ad2 = datetime.time(22, 30)

        border = workbook.add_format({'border': 1})
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
            worksheet.write(row, col, tm.strftime(SHORT_TIME_FORMAT), border)
            # in facts workers
            in_fact = len(stats[tm])
            worksheet.write(row, col+1, in_fact, border)
            # predicted workers
            predicted = list(filter(
                lambda prediction: prediction.dttm_forecast == datetime.datetime.combine(weekday, tm),
                predictions
            ))
            result_prediction = 0
            for prediction in predicted:
                if prediction.cashbox_type.name == 'Линия':
                    result_prediction += prediction.clients / 14
                else:
                    result_prediction += prediction.clients / 4
            if tm_st_ad4 < tm < tm_end_ad4:
                result_prediction += 4
            elif tm_st_ad2 < tm < tm_end_ad2:
                result_prediction += 2
            result_prediction += ct_add
            result_prediction = int(result_prediction + 0.5)
            worksheet.write(row, col+2, result_prediction, border)
            worksheet.write(row, col+3, in_fact - result_prediction, border)
            row += 1

        return row

    def write_stats_summary(workbook, worksheet, stats, last_row):
        centered_border = workbook.add_format({'border': 1, 'align': 'center'})
        row = last_row
        col = 13

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'утро 08:00', centered_border)
        worksheet.write(row, col+3, len(stats[datetime.time(hour=8)]), centered_border)

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'утро 8:00 - 9:30', centered_border)
        worksheet.write(row, col+3, len(stats[datetime.time(hour=9, minute=30)]), centered_border)

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'утро 8:00 - 12:30', centered_border)
        worksheet.write(row, col+3, len(stats[datetime.time(hour=12, minute=30)]), centered_border)

        row += 1
        worksheet.merge_range(row, col, row, col+2, 'вечер', centered_border)
        worksheet.write(row, col+3, len(stats[datetime.time(hour=21)]), centered_border)

        return row

    def write_overtime(workbook, worksheet, last_row):
        gray_bg_color = workbook.add_format({'bg_color': 'gray'})
        border = workbook.add_format({'border': 1})
        row = last_row + 4
        worksheet.write(row, 0, 'Подработка, выход в выходной', gray_bg_color)
        for col in range(1, 11):
            worksheet.write_blank(row, col, '', gray_bg_color)
        row += 1
        for i in range(5):
            for col in range(11):
                worksheet.write_blank(row + i, col, '', border)


    output = io.BytesIO()
    form = GetTable(request.GET)
    if not form.is_valid():
        return JsonResponse.value_error(str(list(form.errors.items())))
    form = form.cleaned_data
    shop_id = form['shop_id']
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
    # prepare data
    dt_start = datetime.date(form['dt'].year, form['dt'].month, 1)
    dt_start_year = datetime.date(dt_start.year, 1, 1)
    dt_tmp = (dt_start + datetime.timedelta(days=31))
    dt_end = datetime.date(dt_tmp.year, dt_tmp.month, 1) - datetime.timedelta(days=1)

    usrs = User.objects.qos_filter_active(dt_start, dt_end)
    # todo: add code for permissions check (check stat of workers from another shops)
    worker_ids = form['worker_ids']

    if (worker_ids is None) or (len(worker_ids) == 0):
        shop_id = form['shop_id']
        if not shop_id:
            shop_id = request.user.shop_id

        usrs = usrs.filter(shop_id=shop_id)
    else:
        usrs = usrs.filter(id__in=worker_ids)
    usrs = usrs.order_by('id')

    usrs_ids = [u.id for u in usrs]

    # count info of current month
    month_info = count_work_month_stats(dt_start, dt_end, usrs)

    # block for count normal amount of working days and working hours
    dts_start_count_dict, _ = count_normal_days(dt_start_year, dt_start, usrs)

    priv_info = list(User.objects.filter(
        Q(workermonthstat__month__dt_first__gte=dt_start_year,
          workermonthstat__month__dt_first__lt=dt_start) |
        Q(workermonthstat=None), # for doing left join
        id__in=usrs_ids,
    ).values('id').annotate(
        count_workdays=Coalesce(Sum('workermonthstat__work_days'), 0),
        count_hours=Coalesce(Sum('workermonthstat__work_hours'), 0),
    ).order_by('id'))

    # add priv_info to user + convert types (fucking idiotism!)

    for u_it in range(len(usrs)):
        dt_u_st = usrs[u_it].dt_hired if usrs[u_it].dt_hired and (usrs[u_it].dt_hired > dt_start_year) else dt_start_year
        total_norm_days, total_norm_hours = dts_start_count_dict[dt_u_st]
        diff_priv_days = priv_info[u_it]['count_workdays'] - total_norm_days
        diff_priv_hours = priv_info[u_it]['count_hours'] - total_norm_hours
    #
        user_info_dict = month_info[usrs[u_it].id]

        user_info_dict.update({
            'diff_priv_paid_days': diff_priv_days,
            'diff_priv_paid_hours': diff_priv_hours,
            'diff_total_paid_days': diff_priv_days + user_info_dict['diff_norm_days'],
            'diff_total_paid_hours': diff_priv_hours + user_info_dict['diff_norm_hours'],
        })

        for day_type in WorkerDay.Type:
            user_info_dict[WorkerDayConverter.convert_type(day_type.value)] = user_info_dict.pop(day_type.value)

        month_info[usrs[u_it].id] = user_info_dict
    return JsonResponse.success({'users_info': month_info})




