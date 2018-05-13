import xlsxwriter
import datetime
import locale
locale.setlocale(locale.LC_ALL, 'ru_RU.utf8')

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


def write_timetable(worksheet, super_shop_code):
    # write global header
    TODAY = datetime.date.today()
    worksheet.write('A1', 'Дата:')
    worksheet.merge_range('B1:C1', TODAY.strftime('%d/%m/%Y'))
    worksheet.merge_range('F1:G1', 'День недели:')
    worksheet.merge_range('H1:K1', TODAY.strftime('%A'))
    worksheet.merge_range('A2:K2', '')

    # write left header
    worksheet.write('A3', 'Фамилия')
    worksheet.merge_range('B3:C3', 'Специализация')
    worksheet.write('D3', 'Время прихода')
    worksheet.write('F3', 'Время ухода')
    worksheet.merge_range('H3:K3', 'Перерывы')

    # write right header
    row = 3
    col = 13
    worksheet.write(row, col, 'Время')
    worksheet.write(row, col+1, 'Факт')
    worksheet.write(row, col+2, 'Должно быть')
    worksheet.write(row, col+3, 'Разница')
    row += 1

    # prepare stats dict
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

    # write user data
    users = User.objects.filter(
        shop__super_shop__code=super_shop_code,
        shop__title="Кассиры",
    )
    row = 3
    for user in users:
        worksheet.write(row, 0, '{} {}'.format(user.last_name, user.first_name))
        rest_time = ['0:00', '0:15', '0:15', '0:45']
        worksheet.write_row(row, 7, rest_time)
        try:
            workerday = WorkerDay.objects.get(
                worker=user,
                dt=datetime.date.today(),
            )
        except WorkerDay.DoesNotExist:
            print("There is no workerday for user with id =", user.id)
            row += 1
            continue
        if workerday.tm_work_start is not None\
            and workerday.tm_work_end is not None:
            worksheet.write(row, 3, workerday.tm_work_start.strftime("%H:%M"))
            worksheet.write(row, 5, workerday.tm_work_end.strftime("%H:%M"))
            for stat_time in stats:
                if stat_time >= workerday.tm_work_start and (\
                    stat_time < workerday.tm_work_end or\
                    workerday.tm_work_end.hour == 0):
                    stats[stat_time].append(workerday)

        row += 1

    # write stats
    row = 4
    col = 13
    for tm in stats:
        worksheet.write(row, col, tm.strftime('%H:%M'))
        in_fact = len(stats[tm])
        worksheet.write(row, col+1, in_fact)
        predicted = PeriodDemand.objects.filter(
            dttm_forecast=datetime.datetime.combine(
                TODAY,
                tm
            )
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

    # write total stats
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



@api_method('GET', GetTable)
def get_table(request, form):
    workbook = xlsxwriter.Workbook('hello.xlsx')
    worksheet = workbook.add_worksheet()

    write_timetable(worksheet, form['super_shop_code'])
    workbook.close()

    return JsonResponse.success()