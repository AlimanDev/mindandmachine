from calendar import monthrange
from datetime import date
import io

import xlsxwriter
from src.base.models import Employee, Employment
from django.db.models.aggregates import Sum
from django.db.models.fields import FloatField
from django.db.models.functions.comparison import Coalesce
from django.db.models.query_utils import Q
from src.timetable.models import PlanAndFactHours, ProdCal, WorkerDay

def overtimes_undertimes(period_step=6, employee_id__in=None, shop_ids=None):
    dt = date.today()
    period_num_within_year = dt.month // period_step
    if dt.month % period_step > 0:
        period_num_within_year += 1
    year = dt.year
    end_month = period_num_within_year * period_step
    start_month = end_month - (period_step - 1)
    dt_from, dt_to = date(year, start_month, 1), \
        date(year, end_month, monthrange(year, end_month)[1])
    print(dt_from, dt_to)
    employee_filter = {}
    if shop_ids:
        employee_filter['id__in'] = Employment.objects.get_active(
            shop_id__in=shop_ids,
        ).values_list('employee_id', flat=True)
    if employee_id__in:
        employee_filter['id__in'] = employee_id__in
    employees = Employee.objects.filter(**employee_filter).select_related('user')
    plan_fact = PlanAndFactHours.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        employee__in=employees,
    ).values(
        'employee_id',
        'dt__month',
    ).annotate(
        plan=Coalesce(
            Sum(
                'plan_work_hours',
                filter=Q(
                    plan_work_hours__gte=0,
                    wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE
                ),
            output_field=FloatField()), 
            0
        ),
        fact=Coalesce(
            Sum(
                'fact_work_hours',
                filter=Q(
                    fact_work_hours__gte=0,
                    wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE
                ),
            output_field=FloatField()), 
            0
        )
    ).order_by('employee__tabel_code')

    prod_cal_qs = ProdCal.objects.filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        employee__in=employees,
    ).values(
        'employee_id',
        'dt__month',
    ).annotate(
        norm=Coalesce(
            Sum('norm_hours'), 
            0
        ),
    ).order_by('employee__tabel_code')

    employee_dict = {}

    for pf in plan_fact:
        employee_dict.setdefault(pf['employee_id'], {}).setdefault(pf['dt__month'], {})['plan'] = pf['plan']
        employee_dict.setdefault(pf['employee_id'], {}).setdefault(pf['dt__month'], {})['fact'] = pf['fact']
        employee_dict.setdefault(pf['employee_id'], {})['plan_sum'] = employee_dict.get(pf['employee_id'],{}).get('plan_sum', 0) + pf['plan']
        employee_dict.setdefault(pf['employee_id'], {})['fact_sum'] = employee_dict.get(pf['employee_id'],{}).get('fact_sum', 0) + pf['fact']

    for prod_cal in prod_cal_qs:
        employee_dict.setdefault(prod_cal['employee_id'], {}).setdefault(prod_cal['dt__month'], {})['norm'] = prod_cal['norm']
        employee_dict.setdefault(prod_cal['employee_id'], {})['norm_sum'] = employee_dict.get(prod_cal['employee_id'],{}).get('norm_sum', 0) + prod_cal['norm']

    res = {
        'data': employee_dict,
        'employees': employees,
    }

    return res

def overtimes_undertimes_xlsx(period_step=6, employee_id__in=None, shop_ids=None, title=None, in_memory=False):
    if not title:
        title = f'Overtimes_undertimes.xlsx'

    FIO = 0
    TABEL_CODE = 1
    NORM_PERIOD = 2
    FACT_PERIOD = 3
    DIFF_PERIOD = 4
    SPACE = 5
    data = overtimes_undertimes(period_step=period_step, employee_id__in=employee_id__in, shop_ids=shop_ids)

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(title)

    worksheet = workbook.add_worksheet('overtimes')
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
    worksheet.write_string(0, FIO, 'ФИО', header_format)
    worksheet.write_string(0, TABEL_CODE, 'Табельный номер', header_format)
    worksheet.write_string(0, NORM_PERIOD, 'Норма за учетный период', header_format)
    worksheet.write_string(0, FACT_PERIOD, 'Отработано на сегодня ({})'.format(date.today().strftime('%d.%m.%Y')), header_format)
    worksheet.write_string(0, DIFF_PERIOD, 'Всего переработки/недоработки ({})'.format(date.today().strftime('%d.%m.%Y')), header_format)
    worksheet.write_string(0, SPACE, '')
    # worksheet.set_column(SHOP_CODE, SHOP_CODE, 10)
    # worksheet.set_column(SHOP, SHOP, 12)
    # worksheet.set_column(TABEL_CODE, TABEL_CODE, 15)
    # worksheet.set_column(DATE, DATE, 15)
    # worksheet.set_column(FIO, FIO, 20)
    # worksheet.set_column(OVERTIME, OVERTIME, 15)
    row = 1
    employees = data['employees']
    data = data['data']
    for employee in employees:
        worksheet.write_string(row, FIO, employee.user.get_fio(), def_format)
        worksheet.write_string(row, TABEL_CODE, employee.tabel_code or '', def_format)
        worksheet.write_string(row, NORM_PERIOD, str(data.get(employee.id, {}).get('norm_sum', 0)), def_format)
        worksheet.write_string(row, FACT_PERIOD, str(data.get(employee.id, {}).get('fact_sum', 0)), def_format)
        worksheet.write_string(row, DIFF_PERIOD, str(data.get(employee.id, {}).get('fact_sum', 0) - data.get(employee.id, {}).get('norm_sum', 0)), def_format)
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
