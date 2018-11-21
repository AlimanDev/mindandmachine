import datetime

from openpyxl import load_workbook
import pandas as pd
import re
from openpyxl.utils import column_index_from_string
from dateutil.relativedelta import relativedelta
from src.util.utils import api_method, JsonResponse
from .utils import get_uploaded_file, WORK_TYPES
from .forms import UploadForm
from src.db.models import (
    User,
    PeriodClients,
    Cashbox,
    Notifications,
    WorkerDay,
    WorkerDayCashboxDetails,
)
from src.main.demand.utils import create_predbills_request_function
from src.util.models_converter import BaseConverter


@api_method(
    'POST',
    UploadForm,
    groups=[User.GROUP_SUPERVISOR, User.GROUP_SUPERVISOR]
)
@get_uploaded_file
def upload_demand(request, form, demand_file):
    """
    Принимает от клиента экселевский файл и загружает из него данные в бд

    Args:
         method: POST
         url: /api/upload/upload_demand
         shop_id(int): required = True
    """
    list_to_create = []

    def create_demand_objs(obj=None):
        if obj is None:
            PeriodClients.objects.bulk_create(list_to_create)
        elif len(list_to_create) == 999:
            list_to_create.append(obj)
            PeriodClients.objects.bulk_create(list_to_create)
            list_to_create[:] = []
        else:
            list_to_create.append(obj)

    def qs_on_date(dt):
        return PeriodClients.objects.filter(
            type=PeriodClients.FACT_TYPE,
            dttm_forecast__date=dt,
            cashbox_type__shop_id=shop_id
        )

    df = pd.read_excel(demand_file)
    df = df.fillna('')
    df = df.values

    ######################### сюда писать логику чтения из экселя ######################################################

    shop_id = form['shop_id']
    date_format = '%m/%d/%Y'
    summ = '∑'
    hours_row = 8  # 10 - 2
    first_date_row = 111  # 113 - 2
    cashbox_col = 2
    values_start_col = 4

    date_to_create = datetime.datetime.strptime(df[first_date_row][0], date_format).date()

    cashboxes = Cashbox.objects.select_related('type').filter(
        type__shop_id=shop_id
    )
    cashboxes_numbers = list(cashboxes.values_list('number', flat=True))
    cashboxes_not_found = []
    cashbox_types = {}
    for cashbox in cashboxes:
        cashbox_types[cashbox.number] = cashbox.type_id

    hours = []
    for hour in df[hours_row]:
        if hour and hour != summ:
            hours.append(datetime.time(int(hour), 0))
            hours.append(datetime.time(int(hour), 30))
    hours.pop(1)  # pop 0:30


    start = datetime.datetime.now()

    for row_ind, row in enumerate(df[hours_row + 1:]):
        if row_ind % 3 != 0:
            continue
        cashbox_num = row[cashbox_col]
        if cashbox_num == summ:
            continue
        if not len(cashbox_num):  # нашли дату
            if '.' in row[0] or '/' in row[0]:  # проверим, что она похожа на формат даты
                date_to_create = datetime.datetime.strptime(row[0], date_format).date()
            continue
        else:
            cashbox_num = int(cashbox_num)

        if cashbox_num in cashboxes_numbers:
            cashbox_type_id = cashbox_types[cashbox_num]
            qs_on_date(date_to_create).filter(cashbox_type_id=cashbox_type_id).delete()
            for hour_ind, hour in enumerate(hours):
                df_hour_index = values_start_col + int((hour_ind+1)/2)
                value = row[df_hour_index]
                if hour_ind != 0 and hour_ind % 2 == 0 and hour_ind != len(hours) - 1:
                    value = value + row[df_hour_index + 1] / 2
                create_dict = {
                    'type': PeriodClients.FACT_TYPE,
                    'dttm_forecast': datetime.datetime.combine(date_to_create, hour),
                    'cashbox_type_id': cashbox_type_id
                }
                filtered_list = list(filter(lambda x:
                                            x.dttm_forecast == datetime.datetime.combine(date_to_create, hour)
                                            and x.cashbox_type_id == cashbox_type_id,
                                            list_to_create))
                if filtered_list:
                    filtered_list[0].value += value
                else:
                    create_demand_objs(PeriodClients(value=value, **create_dict))
        else:
            cashboxes_not_found.append(cashbox_num)
    ####################################################################################################################

    create_demand_objs(None)

    cashboxes_not_found = list(set(cashboxes_not_found))

    if cashboxes_not_found:
        for u in User.objects.filter(shop_id=shop_id, group__in=User.__except_cashiers__):
            Notifications.objects.create(
                to_worker_id=u.id,
                text='Был составлен прогноз по клиентам. Кассы с номера {} не были найдены в базе данных.'.format(cashboxes_not_found),
                type=Notifications.TYPE_INFO
            )

    from_dt_to_create = PeriodClients.objects.filter(
        type=PeriodClients.FACT_TYPE,
        cashbox_type__shop_id=shop_id
    ).order_by('dttm_forecast').last().dttm_forecast.date() + relativedelta(days=1)

    result_of_func = create_predbills_request_function(shop_id=shop_id, dt=from_dt_to_create)

    return JsonResponse.success() if result_of_func is True else result_of_func


@api_method(
    'POST',
    UploadForm,
    groups=[User.GROUP_SUPERVISOR, User.GROUP_DIRECTOR]
)
@get_uploaded_file
def upload_timetable(request, form, timetable_file):
    """
    Принимает от клиента экселевский файл и создает расписание (на месяц)

    Args:
         method: POST
         url: /api/upload/upload_timetable
         shop_id(int): required = True
    """
    shop_id = form['shop_id']

    try:
        worksheet = load_workbook(timetable_file).active
    except KeyError:
        return JsonResponse.internal_error('Не удалось открыть активный лист.')

    ######################### сюда писать логику чтения из экселя ######################################################
    fio_column = 2
    workers_start_row = 19
    dates_row = 17
    dates_start_column = 5

    work_dates = []
    for column in worksheet.iter_cols(min_col=dates_start_column, min_row=dates_row, max_row=dates_row):
        for cell in column:
            if isinstance(cell.value, datetime.datetime):
                work_dates.append(cell.value.date())
    dates_end_column = dates_start_column + len(work_dates) - 1

    if not work_dates:
        return JsonResponse.value_error('Не смог сгенерировать массив дат. Возможно они в формате строки.')

    for row in worksheet.iter_rows(min_row=workers_start_row):
        for cell in row:
            if column_index_from_string(cell.column) == fio_column:
                first_last_names = cell.value.split(' ')
                last_name_concated = ' '.join(first_last_names[:-2])
                try:
                    u = User.objects.get(shop_id=shop_id, last_name=last_name_concated, first_name=first_last_names[-2])
                except User.DoesNotExist:
                    return JsonResponse.value_error('Не могу найти пользователя на строке {}'.format(cell.row))
            column_index = column_index_from_string(cell.column)
            if dates_start_column <= column_index <= dates_end_column:
                dt = work_dates[column_index - dates_start_column]
                dttm_work_start = None
                dttm_work_end = None
                #  todo: если будут типы с цифрами, надо будет переделать
                if bool(re.search(r'\d', cell.value)):
                    times = cell.value.split('-')
                    work_type = WorkerDay.Type.TYPE_WORKDAY.value
                    dttm_work_start = datetime.datetime.combine(
                        dt, BaseConverter.parse_time(times[0] + ':00')
                    )
                    dttm_work_end = datetime.datetime.combine(
                        dt, BaseConverter.parse_time(times[1] + ':00')
                    )
                    if dttm_work_end < dttm_work_start:
                        dttm_work_start += datetime.timedelta(days=1)
                else:
                    work_type = WORK_TYPES[cell.value]

                wd_query_set = WorkerDay.objects.filter(dt=dt, worker=u)
                WorkerDayCashboxDetails.objects.filter(
                    worker_day__in=wd_query_set
                ).delete()
                for wd in wd_query_set.order_by('-id'):  # потому что могут быть родители у wd
                    wd.delete()
                new_wd = WorkerDay.objects.create(
                    worker=u,
                    dt=dt,
                    dttm_work_start=dttm_work_start,
                    dttm_work_end=dttm_work_end,
                    type=work_type
                )
                if work_type == WorkerDay.Type.TYPE_WORKDAY.value:
                    WorkerDayCashboxDetails.objects.create(
                        worker_day=new_wd,
                        dttm_from=dttm_work_start,
                        dttm_to=dttm_work_end,
                        status=WorkerDayCashboxDetails.TYPE_WORK,

                    )

    ####################################################################################################################

    return JsonResponse.success()
