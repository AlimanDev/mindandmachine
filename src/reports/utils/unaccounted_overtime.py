import io
from django.db.models.functions import Greatest, Extract, Cast
from django.db.models import F, IntegerField

from datetime import date, timedelta

import xlsxwriter
from src.base.models import Employment
from src.timetable.models import WorkerDay


def get_unaccounted_overtimes(network_id, dt_from=None, dt_to=None, shop_ids=None, user_ids=None):
    filter_values = {}
    if shop_ids:
        filter_values['shop_id__in'] = shop_ids
    if user_ids:
        filter_values['employee__user_id__in'] = user_ids
    if not dt_from or not dt_to:
        dt_from = date.today() - timedelta(1)
        dt_to = date.today() - timedelta(1)
    employee_ids = Employment.objects.get_active(
        network_id,
        dt_from=dt_from,
        dt_to=dt_to,
        **filter_values,
    ).values_list('employee_id', flat=True)
    filter_values.pop('employee__user_id__in', None)
    return WorkerDay.objects.filter(
        employee_id__in=employee_ids,
        type__is_dayoff=False,
        type__is_work_hours=True,
        shop__isnull=False,
        dt__gte=dt_from,
        dt__lte=dt_to,
        is_fact=True,
        is_approved=True,
        dttm_work_start__isnull=False,
        dttm_work_end__isnull=False,
        dttm_work_start_tabel__isnull=False,
        dttm_work_end_tabel__isnull=False,
        **filter_values,
    ).annotate(
        overtime_start=Greatest(Cast(Extract(F('dttm_work_start_tabel') - F('dttm_work_start'), 'epoch'), IntegerField()), 0),
        overtime_end=Greatest(Cast(Extract(F('dttm_work_end') - F('dttm_work_end_tabel'), 'epoch'), IntegerField()), 0),
        overtime=F('overtime_start') + F('overtime_end'),
    ).filter(
        overtime__gte=3600,
    ).select_related(
        'employee',
        'employee__user',
        'shop',
    ).order_by(
        'dt',
        'employee_id',
    )


def unaccounted_overtimes_xlsx(network_id, dt_from=None, dt_to=None, title=None, shop_ids=None, in_memory=False):
    if not dt_from:
        dt_from = date.today() - timedelta(1)
    if not dt_to:
        dt_to = dt_from
    if not title:
        title = f'Unaccounted_overtimes_{dt_from}-{dt_to}.xlsx'
    DATE = 0
    SHOP_CODE = 1
    SHOP = 2
    TABEL_CODE = 3
    FIO = 4
    OVERTIME = 5
    data = get_unaccounted_overtimes(network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=shop_ids)

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)

    worksheet = workbook.add_worksheet('{}-{}'.format(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d')))
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
    worksheet.write_string(0, DATE, 'Дата', header_format)
    worksheet.write_string(0, OVERTIME, 'Неучтенные переработки', header_format)
    worksheet.set_column(SHOP_CODE, SHOP_CODE, 10)
    worksheet.set_column(SHOP, SHOP, 12)
    worksheet.set_column(TABEL_CODE, TABEL_CODE, 15)
    worksheet.set_column(DATE, DATE, 15)
    worksheet.set_column(FIO, FIO, 20)
    worksheet.set_column(OVERTIME, OVERTIME, 15)
    row = 1
    for overtime in data:
        overtime_text = 'более ' + ('1 часа' if overtime.overtime // 3600 == 1 else f'{overtime.overtime // 3600} часов')
        worksheet.write_string(row, SHOP_CODE, overtime.shop.code or '', def_format)
        worksheet.write_string(row, SHOP, overtime.shop.name, def_format)
        worksheet.write_string(row, TABEL_CODE, overtime.employee.tabel_code or '', def_format)
        worksheet.write_string(row, DATE, overtime.dt.strftime('%d.%m.%Y'), def_format)
        worksheet.write_string(row, FIO, overtime.employee.user.get_fio(), def_format)
        worksheet.write_string(row, OVERTIME, overtime_text, def_format)
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
