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
    CashboxType,
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
def upload_demand(request, form):
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
    #
    # df = pd.read_excel(demand_file)
    # df = df.fillna('')
    # df = df.values
    print('here')
    # print(df)

    ######################### сюда писать логику чтения из экселя ######################################################

    shop_id = form['shop_id']
    date_format = '%d/%m/%Y'
    summ = '∑'
    hours_row = 8  # 10 - 2
    first_date_row = 111  # 113 - 2
    cashbox_col = 2
    values_start_col = 4

    # date_to_create = datetime.datetime.strptime(df[first_date_row][0], date_format).date()

    cashboxes = Cashbox.objects.select_related('type').filter(
        type__shop_id=shop_id
    )
    cashboxes_numbers = list(cashboxes.values_list('number'))
    cashboxes_not_found = []
    cashbox_types = {}
    for cashbox in cashboxes:
        cashbox_types[cashbox.number] = cashbox.type_id

    # hours = []
    # for hour in df[hours_row]:
    #     if hour and hour != summ:
    #         hours.append(datetime.time(int(hour), 0))
    #
    # hours_len = len(hours)
    #
    # for row_ind, row in enumerate(df[hours_row + 1:]):
    #     if row_ind == df.shape[0]:
    #         break
    #     if row_ind % 3 != 0:
    #         continue
        # print(row_ind)
        # cashbox_num = row[cashbox_col]
        # if not len(cashbox_num):  # нашли дату
            # print(row_ind, row[0])
            # date_to_create = datetime.datetime.strptime(row[0], date_format).date()
        # if cashbox_num in cashboxes_numbers:
        #     pass
        #     prev_value = None  # так как шаг в час, будем брать среднее между соседними часами
        #     for col_ind, value in enumerate(row[values_start_col: values_start_col + hours_len]):
        #         if prev_value:
        #             create_demand_objs(
        #                 PeriodClients(
        #                     type=PeriodClients.FACT_TYPE,
        #                     value=(prev_value + value) / 2,
        #                     dttm_forecast=datetime.datetime.combine(date_to_create, hours[col_ind]) - datetime.timedelta(minutes=30),
        #                     cashbox_type_id=cashbox_types[cashbox_num]
        #                 )
        #             )
        #         create_demand_objs(
        #             PeriodClients(
        #                 type=PeriodClients.FACT_TYPE,
        #                 value=value,
        #                 dttm_forecast=datetime.datetime.combine(date_to_create, hours[col_ind])
        #             )
        #         )
        #         prev_value = value
        # else:
        #     cashboxes_not_found.append(cashbox_num)


    # for index, row in enumerate(worksheet.rows):
    #     value = row[value_column_num].value
    #     if not isinstance(row[value_column_num].value, int):
    #         #  может быть 'Нет данных'
    #         continue
    #     checked_rows += 1
    #     dttm = row[time_column_num].value
    #     if '.' not in dttm or ':' not in dttm:
    #         continue
    #     if not isinstance(dttm, datetime.datetime):
    #         try:
    #             dttm = datetime.datetime.strptime(dttm, datetime_format)
    #         except ValueError:
    #             return JsonResponse.value_error('Невозможно преобразовать время. Пожалуйста введите формат {}'.format(datetime_format))
    #
    #     cashtype_name = row[cash_column_num].value
    #     cashtype_name = cashtype_name[:1].upper() + cashtype_name[1:].lower()  # учет регистра чтобы нормально в бд было
    #
    #     ct_to_search = list(filter(lambda ct: ct.name == cashtype_name, cashbox_types))  # возвращает фильтр по типам
    #     if len(ct_to_search) == 1:
    #         PeriodClients.objects.filter(
    #             dttm_forecast=dttm,
    #             cashbox_type=ct_to_search[0],
    #             type=PeriodClients.FACT_TYPE
    #         ).delete()
    #         create_demand_objs(
    #             PeriodClients(
    #                 dttm_forecast=dttm,
    #                 cashbox_type=ct_to_search[0],
    #                 value=value,
    #                 type=PeriodClients.FACT_TYPE
    #             )
    #         )
    #         processed_rows += 1
    #
    #     else:
    #         return JsonResponse.internal_error('Невозможно прочитать тип работ на строке №{}.'.format(index))
    #
    # if processed_rows == 0 or processed_rows < checked_rows / 2:  # если было обработано, меньше половины строк, че-то пошло не так
    #     return JsonResponse.internal_error(
    #         'Было обработано {}/{} строк. Пожалуйста, проверьте формат данных в файле.'.format(
    #             processed_rows, worksheet.max_row
    #         )
    #     )

    ####################################################################################################################

    create_demand_objs(None)

    # print(list(set(cashboxes_not_found)))

    # from_dt_to_create = PeriodClients.objects.filter(
    #     type=PeriodClients.FACT_TYPE,
    #     cashbox_type__shop_id=shop_id
    # ).order_by('dttm_forecast').last().dttm_forecast.date() + relativedelta(days=1)
    #
    # result_of_func = create_predbills_request_function(shop_id=shop_id, dt=from_dt_to_create)

    return JsonResponse.success()# if result_of_func is True else result_of_func


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
