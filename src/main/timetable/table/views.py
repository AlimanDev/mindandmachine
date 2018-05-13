import xlsxwriter
import datetime
import locale
import io
locale.setlocale(locale.LC_ALL, 'ru_RU.utf8')

from django.http import HttpResponse
from src.util.utils import JsonResponse
from src.db.models import User, WorkerCashboxInfo, WorkerDay, PeriodDemand
from src.util.models_converter import UserConverter
from src.util.utils import api_method, JsonResponse
from .forms import SelectCashiersForm, GetTable

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


def write_global_header(worksheet, today):
    worksheet.write('A1', 'Дата:')
    worksheet.merge_range('B1:C1', today.strftime('%d/%m/%Y'))
    worksheet.merge_range('F1:G1', 'День недели:')
    worksheet.merge_range('H1:K1', today.strftime('%A'))
    worksheet.merge_range('A2:K2', '')


def write_workers_header(worksheet):
    worksheet.write('A3', 'Фамилия')
    worksheet.merge_range('B3:C3', 'Специализация')
    worksheet.write('D3', 'Время прихода')
    worksheet.write('F3', 'Время ухода')
    worksheet.merge_range('H3:K3', 'Перерывы')


def write_stats_header(worksheet):
    worksheet.write('N3', 'Время')
    worksheet.write('O3', 'Факт')
    worksheet.write('P3', 'Должно быть')
    worksheet.write('Q3', 'Разница')


def create_stats_dictionary():
    stats = {}
    tm = datetime.datetime.combine(
        datetime.date.today(),
        datetime.time(hour=7)
    )
    tm_step = datetime.timedelta(
        minutes=30
    )
    tm_end = datetime.datetime.combine(
        datetime.date.today(),
        datetime.time(hour=23, minute=59)
    )
    before_start = datetime.time(hour=6, minute=45)
    stats[before_start] = []
    while tm < tm_end:
        tm += tm_step
        stats[tm.time()] = []

    return stats


def write_users(worksheet, super_shop_code, stats):
    # TODO: move status updation to other function
    local_stats = dict(stats)
    users = User.objects.filter(
        shop__super_shop__code=super_shop_code,
        shop__title="Кассиры",
    )
    row = 3
    for user in users:
        try:
            workerday = WorkerDay.objects.get(
                worker=user,
                dt=datetime.date.today(),
            )
            if workerday.tm_work_start is None\
                or workerday.tm_work_end is None:
                continue
            # user data
            worksheet.write(row, 0, '{} {}'.format(user.last_name, user.first_name))
            # rest time
            rest_time = ['0:00', '0:15', '0:15', '0:45']
            worksheet.write_row(row, 7, rest_time)
            # start and end time
            worksheet.write(row, 3, workerday.tm_work_start.strftime("%H:%M"))
            worksheet.write(row, 5, workerday.tm_work_end.strftime("%H:%M"))
            # update stats
            for stat_time in local_stats:
                if stat_time >= workerday.tm_work_start and (\
                    stat_time < workerday.tm_work_end or\
                    workerday.tm_work_end.hour == 0):
                    local_stats[stat_time].append(workerday)
            row += 1

        except WorkerDay.DoesNotExist:
            continue

    return local_stats


def write_stats(worksheet, stats, today, super_shop_code):
    # write stats
    row = 3
    col = 13
    for tm in stats:
        worksheet.write(row, col, tm.strftime('%H:%M'))
        # in facts workers
        in_fact = len(stats[tm])
        worksheet.write(row, col+1, in_fact)
        # predicted workers
        predicted = PeriodDemand.objects.filter(
            dttm_forecast=datetime.datetime.combine(
                today,
                tm
            ),
            cashbox_type__shop__super_shop__code=super_shop_code
        )
        result_prediction = 0
        for prediction in predicted:
            if prediction.cashbox_type.name == 'Линия':
                result_prediction += prediction.clients/15
            else:
                result_prediction += prediction.clients/5
        result_prediction = int(result_prediction)
        worksheet.write(row, col+2, result_prediction)
        worksheet.write(row, col+3, abs(in_fact - result_prediction))
        row += 1

    return row


def write_stats_summary(worksheet, stats, last_row):
    row = last_row
    col = 13

    row += 1
    worksheet.merge_range(row, col, row, col+2, 'утро 08:00')
    worksheet.write(row, col+3, len(stats[datetime.time(hour=8)]))

    row += 1
    worksheet.merge_range(row, col, row, col+2, 'утро 8:00 - 9:30')
    worksheet.write(row, col+3, len(stats[datetime.time(hour=9, minute=30)]))

    row += 1
    worksheet.merge_range(row, col, row, col+2, 'утро 8:00 - 12:30')
    worksheet.write(row, col+3, len(stats[datetime.time(hour=12, minute=30)]))

    row += 1
    worksheet.merge_range(row, col, row, col+2, 'вечер')
    worksheet.write(row, col+3, len(stats[datetime.time(hour=21)]))


def get_table(request):
    output = io.BytesIO()
    form = GetTable(request.GET)
    if not form.is_valid():
        return JsonResponse.value_error(str(list(form.errors.items())))
    form = form.cleaned_data
    super_shop_code = form['super_shop_code']
    today = datetime.date.today()

    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    # workbook = xlsxwriter.Workbook('hello.xlsx')
    worksheet = workbook.add_worksheet()
    worksheet.set_column(0, 0, 23)

    write_global_header(worksheet, today)
    write_workers_header(worksheet)
    write_stats_header(worksheet)

    stats = create_stats_dictionary()
    stats = write_users(worksheet, super_shop_code, stats)
    last_row = write_stats(worksheet, stats, today, super_shop_code)
    write_stats_summary(worksheet, stats, last_row)

    workbook.close()
    output.seek(0)

    response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename="table.xlsx"'

    return response