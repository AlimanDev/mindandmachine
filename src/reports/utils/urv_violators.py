from src.timetable.models import WorkerDay, AttendanceRecords
from src.base.models import Shop, User, Employment, Employee
import xlsxwriter
import io
from datetime import date, datetime, timedelta
from django.db.models import Sum, Q, Count, Exists, OuterRef
from django.db.models.functions import Trunc
from dateutil.relativedelta import relativedelta

NO_RECORDS = 'R'
NO_COMMING = 'C'
NO_LEAVING = 'L'
NO_COMING_PROBABLY = 'CP'
BAD_FACT = 'BF'
BAD_FACT_NO_COMMING = 'BFC'
BAD_FACT_NO_LEAVING = 'BFL'

NO_COMMING_HOURS = 4

text = {
    NO_RECORDS: 'Нет отметок',
    NO_COMMING: 'Нет прихода',
    NO_LEAVING: 'Нет ухода',
    NO_COMING_PROBABLY: 'Предположительно нет отметки о приходе',
    BAD_FACT: 'Выход не по плану',
    BAD_FACT_NO_COMMING: 'Выход не по плану\nНет прихода',
    BAD_FACT_NO_LEAVING: 'Выход не по плану\nНет ухода',
}


def urv_violators_report(network_id, dt_from=None, dt_to=None, exclude_created_by=False, shop_ids=None, user_ids=None):
    filter_values = {}
    if shop_ids:
        filter_values['shop_id__in'] = shop_ids
    if user_ids:
        filter_values['employee__user_id__in'] = user_ids
    if not dt_from or not dt_to:
        dt_from = date.today() - timedelta(1)
        dt_to = date.today() - timedelta(1)
    data = {}
    employee_ids = Employment.objects.get_active(
        network_id,
        dt_from=dt_from,
        dt_to=dt_to,
        **filter_values,
    ).values_list('employee_id', flat=True)
    filter_values.pop('employee__user_id__in', None)
    no_comming = WorkerDay.objects.filter(
        employee_id__in=employee_ids,
        dt__gte=dt_from,
        dt__lte=dt_to,
        is_fact=True,
        is_approved=True,
        **filter_values,
    )
    if exclude_created_by:
        no_comming = no_comming.annotate(
            exist_records=Exists(
            AttendanceRecords.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    type=AttendanceRecords.TYPE_COMING,
                )
            )
        ).filter(
            exist_records=False,
        )
    else:
        no_comming = no_comming.filter(
            dttm_work_start__isnull=True,
        )
    no_leaving = WorkerDay.objects.filter(
        employee_id__in=employee_ids,
        dt__gte=dt_from,
        dt__lte=dt_to,
        is_fact=True,
        is_approved=True,
        **filter_values,
    )
    if exclude_created_by:
        no_leaving = no_leaving.annotate(
            exist_records=Exists(
            AttendanceRecords.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    type=AttendanceRecords.TYPE_LEAVING,
                )
            )
        ).filter(
            exist_records=False,
        )
    else:
        no_leaving = no_leaving.filter(
            dttm_work_end__isnull=True,
        )
    worker_days = WorkerDay.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        shop__network_id=network_id,
        type=WorkerDay.TYPE_WORKDAY,
        is_approved=True,
        is_fact=False,
        employee_id__in=employee_ids,
        **filter_values,
    )
    
    for record in no_comming:
        data.setdefault(record.employee_id, {})[record.dt] = {
            'shop_id': record.shop_id,
            'type': NO_COMMING,
        }

    for record in no_leaving:
        data.setdefault(record.employee_id, {})[record.dt] = {
            'shop_id': record.shop_id,
            'type': NO_LEAVING,
        }
    
    fact_without_plan = WorkerDay.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        shop__network_id=network_id,
        type=WorkerDay.TYPE_WORKDAY,
        is_approved=True,
        is_fact=True,
        employee_id__in=employee_ids,
        **filter_values,
    ).annotate(
        exist_plan=Exists(
            WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                dt=OuterRef('dt'),
                is_fact=False,
                is_approved=True
            )
        )
    ).filter(
        exist_plan=False,
    )
    for record in fact_without_plan:
        type = data.get(record.employee_id, {}).get(record.dt, {}).get('type', BAD_FACT)
        if type == NO_COMMING:
            type = BAD_FACT_NO_COMMING
        elif type == NO_LEAVING:
            type = BAD_FACT_NO_LEAVING
        data.setdefault(record.employee_id, {})[record.dt] = {
            'shop_id': record.shop_id,
            'type': type,
        }

    if exclude_created_by:
        no_records = worker_days.annotate(
            exist_records=Exists(
                AttendanceRecords.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                )
            )
        ).filter(
            exist_records=False,
        )
    else:
        no_records = worker_days.annotate(
            exist_fact=Exists(
                WorkerDay.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=True,
                    is_approved=True
                )
            )
        ).filter(
            exist_fact=False,
        )
    for record in no_records:
        first_key = record.employee_id
        second_key = record.dt
        data.setdefault(first_key, {})[second_key] = {
            'shop_id': record.shop_id,
            'type': NO_RECORDS,
        } 

    return data


def urv_violators_report_xlsx(network_id, dt=None, title=None, shop_ids=None, in_memory=False):
    if not dt:
        dt = date.today() - timedelta(1)
    if not title:
        title = f'URV_violators_report_{dt}.xlsx'
    SHOP_CODE = 0
    SHOP = 1
    TABEL_CODE = 2
    FIO = 3
    REASON = 4
    shop_filter = {}
    if shop_ids:
        shop_filter['id__in'] = shop_ids
    shops = { 
        s.id: s for s in Shop.objects.filter(**shop_filter)
    }
    data = urv_violators_report(network_id, dt_from=dt, dt_to=dt, shop_ids=shop_ids, exclude_created_by=True)
    employees = {
        e.id: e for e in Employee.objects.select_related('user').filter(
            id__in=data.keys(),
        )
    }

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)
    
    rows = [
        {
            'shop': shops.get(reason['shop_id'], Shop()).name or '',
            'shop_code': shops.get(reason['shop_id'], Shop()).code or '',
            'tabel': employees.get(employee_id).tabel_code or '',
            'fio': employees.get(employee_id).user.fio,
            'reason': text.get(reason['type']),
        }
        for employee_id, record in data.items()
        for dt, reason in record.items()
    ]
    rows = sorted(rows, key=lambda x: x['shop'])

    worksheet = workbook.add_worksheet('{}'.format(dt.strftime('%Y.%m.%d')))
    def_format = workbook.add_format({
        'border': 1,
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True,
    })
    header_format = workbook.add_format({
        'border': 1,
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
    })
    worksheet.write_string(0, SHOP_CODE, 'Код объекта', header_format)
    worksheet.write_string(0, SHOP, 'Название объекта', header_format)
    worksheet.write_string(0, TABEL_CODE, 'Табельный номер', header_format)
    worksheet.write_string(0, FIO, 'ФИО', header_format)
    worksheet.write_string(0, REASON, 'Нарушение', header_format)
    worksheet.set_column(SHOP_CODE, SHOP_CODE, 10)
    worksheet.set_column(SHOP, SHOP, 12)
    worksheet.set_column(TABEL_CODE, TABEL_CODE, 15)
    worksheet.set_column(FIO, FIO, 20)
    worksheet.set_column(REASON, REASON, 15)
    row = 1
    for record in rows:
        worksheet.write_string(row, SHOP_CODE, record['shop_code'], def_format)
        worksheet.write_string(row, SHOP, record['shop'], def_format)
        worksheet.write_string(row, TABEL_CODE, record['tabel'], def_format)
        worksheet.write_string(row, FIO, record['fio'], def_format)
        worksheet.write_string(row, REASON, record['reason'], def_format)
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
    

def urv_violators_report_xlsx_v2(network_id, dt_from=None, dt_to=None, title=None, in_memory=False, exclude_created_by=False, user_ids=None, shop_ids=None):
    if not dt_from:
        dt_from = date.today().replace(day=1)
    if not dt_to:
        dt_to = dt_from + relativedelta(day=31)
    if not title:
        title = f'URV_violators_report_{dt_from}-{dt_to}.xlsx'
    SHOP_CODE = 0
    SHOP = 1
    TABEL_CODE = 2
    FIO = 3
    POSITION = 4
    shops = { 
        s.id: s for s in Shop.objects.all()
    }
    data = urv_violators_report(network_id, dt_from=dt_from, dt_to=dt_to, exclude_created_by=exclude_created_by, user_ids=user_ids, shop_ids=shop_ids)

    employees = {
        e.id: e for e in Employee.objects.select_related('user').filter(
            id__in=data.keys(),
        )
    }

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)
    
    rows = []

    for employee_id, records in data.items():
        empl = Employment.objects.get_active(
            network_id,
            dt_from,
            dt_to,
            employee_id=employee_id,
        ).select_related('position').first()
        rows.append(
            {
                'shop': shops.get(empl.shop_id if empl else None, Shop()).name or '',
                'shop_code': shops.get(empl.shop_id if empl else None, Shop()).code or '',
                'empl': empl,
                'fio': employees.get(employee_id).user.fio,
                'employee': employees.get(employee_id),
                'records': records, 
            }
        ) 

    rows = sorted(rows, key=lambda x: x['shop'])


    worksheet = workbook.add_worksheet('{}-{}'.format(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d')))
    def_format = {
        'border': 1,
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True,
    }
    header_format = {
        'border': 1,
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
    }
    worksheet.write_string(0, SHOP_CODE, 'Код магазина', workbook.add_format(header_format))
    worksheet.write_string(0, SHOP, 'Магазин', workbook.add_format(header_format))
    worksheet.write_string(0, TABEL_CODE, 'Табельный номер', workbook.add_format(header_format))
    worksheet.write_string(0, FIO, 'ФИО', workbook.add_format(header_format))
    worksheet.write_string(0, POSITION, 'Должность', workbook.add_format(header_format))
    worksheet.set_column(SHOP_CODE, SHOP_CODE, 15)
    worksheet.set_column(SHOP, SHOP, 15)
    worksheet.set_column(FIO, FIO, 20)
    worksheet.set_column(POSITION, POSITION, 20)
    worksheet.set_column(TABEL_CODE, TABEL_CODE, 15)
    dates = [dt_from + timedelta(i) for i in range((dt_to - dt_from).days + 1)]
    col = POSITION
    for dt in dates:
        col += 1
        worksheet.write_string(0, col, dt.strftime('%d.%m.%Y'), workbook.add_format(header_format))
        worksheet.set_column(col, col, 10)
    row = 1
    for record in rows:
        worksheet.write_string(row, SHOP_CODE, record['shop_code'] or '', workbook.add_format(def_format))
        worksheet.write_string(row, SHOP, record['shop'], workbook.add_format(def_format))
        worksheet.write_string(row, TABEL_CODE, record['employee'].tabel_code or '', workbook.add_format(def_format))
        worksheet.write_string(row, FIO, record['fio'], workbook.add_format(def_format))
        worksheet.write_string(row, POSITION, record['empl'].position.name if record['empl'] and record['empl'].position else '', workbook.add_format(def_format))
        col = POSITION
        for dt in dates:
            col += 1
            worksheet.write_string(row, col, text.get(record['records'].get(dt, {}).get('type', ''), ''), workbook.add_format(def_format))
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
