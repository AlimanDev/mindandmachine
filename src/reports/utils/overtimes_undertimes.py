from calendar import monthrange
from datetime import date
import io
from src.util.dg.helpers import MONTH_NAMES

from django.db.models.fields import FloatField
from src.reports.helpers import RoundWithPlaces
from dateutil.relativedelta import relativedelta
from django.utils.translation import gettext as _

import xlsxwriter
from src.base.models import Employee, Employment, ProductionDay
from django.db.models import Sum, Q
from django.db.models.functions import Coalesce
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
    celebration_dates = ProductionDay.objects.filter(dt__gte=dt_from, dt__lte=dt_to, is_celebration=True).values_list('dt', flat=True)
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
            RoundWithPlaces(
                Sum(
                    'plan_work_hours',
                    filter=Q(
                        plan_work_hours__gte=0,
                        wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE
                    ) & ~Q(dt__in=celebration_dates),
                    output_field=FloatField(),
                ), 
                1,
            ),
            0
        ),
        fact=Coalesce(
            RoundWithPlaces(
                Sum(
                    'fact_work_hours',
                    filter=Q(
                        fact_work_hours__gte=0,
                        wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE
                    ) & ~Q(dt__in=celebration_dates),
                    output_field=FloatField(),
                ), 
                1,
            ),
            0
        ),
        fact_celebration=Coalesce(
            RoundWithPlaces(
                Sum(
                    'fact_work_hours',
                    filter=Q(
                        fact_work_hours__gte=0,
                        wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE
                    ) & Q(dt__in=celebration_dates),
                    output_field=FloatField(),
                ), 
                1,
            ),
            0
        ),
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
            RoundWithPlaces(Sum('norm_hours', filter=~Q(dt__in=celebration_dates)), 1), 
            0
        ),
        norm_celebration=Coalesce(
            RoundWithPlaces(Sum('norm_hours', filter=Q(dt__in=celebration_dates)), 1), 
            0
        ),
    ).order_by('employee__tabel_code')

    employee_dict = {}

    for pf in plan_fact:
        employee_dict.setdefault(pf['employee_id'], {}).setdefault(pf['dt__month'], {})['plan'] = pf['plan']
        employee_dict.setdefault(pf['employee_id'], {}).setdefault(pf['dt__month'], {})['fact'] = pf['fact']
        employee_dict.setdefault(pf['employee_id'], {}).setdefault(pf['dt__month'], {})['fact_celebration'] = pf['fact_celebration']
        employee_dict.setdefault(pf['employee_id'], {})['plan_sum'] = employee_dict.get(pf['employee_id'],{}).get('plan_sum', 0) + pf['plan']
        employee_dict.setdefault(pf['employee_id'], {})['fact_sum'] = employee_dict.get(pf['employee_id'],{}).get('fact_sum', 0) + pf['fact']

    for prod_cal in prod_cal_qs:
        employee_dict.setdefault(prod_cal['employee_id'], {}).setdefault(prod_cal['dt__month'], {})['norm'] = prod_cal['norm']
        employee_dict.setdefault(prod_cal['employee_id'], {}).setdefault(prod_cal['dt__month'], {})['norm_celebration'] = prod_cal['norm_celebration']
        employee_dict.setdefault(prod_cal['employee_id'], {})['norm_sum'] = employee_dict.get(prod_cal['employee_id'],{}).get('norm_sum', 0) + prod_cal['norm']

    res = {
        'data': employee_dict,
        'employees': employees,
        'months': [(dt_from + relativedelta(months=i)).month for i in range(period_step)]
    }

    return res

def overtimes_undertimes_xlsx(period_step=6, employee_id__in=None, shop_ids=None, title=None, in_memory=False):
    def _generate_months_stat(worksheet: xlsxwriter.Workbook.worksheet_class, start, months, title, format):
        if len(months) > 1:
            worksheet.merge_range(0, start, 0, start + len(months) - 1, title, format)
        else:
            worksheet.write_string(0, start, title, format)
            worksheet.set_column(start, start, 23)
        for i, month in enumerate(months):
            worksheet.write_string(1, start + i, str(MONTH_NAMES[month]), format)
            if len(months) <= 1:
                continue
            worksheet.set_column(start + i, start + i, 10)
        return start + len(months)

    def _fill_month_stat(worksheet: xlsxwriter.Workbook.worksheet_class, start, row, months, data_getter, format):
        for i, month in enumerate(months):
            worksheet.write_string(row, start + i, str(data_getter(month)), format)
    
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
    worksheet.write_string(0, SPACE, '')
    worksheet.merge_range(0, FIO, 1, FIO, _('Full name'), header_format)
    worksheet.merge_range(0, TABEL_CODE, 1, TABEL_CODE, _('Employee id'), header_format)
    worksheet.merge_range(0, NORM_PERIOD, 1, NORM_PERIOD, _('The norm for the accounting period'), header_format) 
    worksheet.merge_range(0, FACT_PERIOD, 1, FACT_PERIOD, _('Worked out for today ({})').format(date.today().strftime('%d.%m.%Y')), header_format)
    worksheet.merge_range(0, DIFF_PERIOD, 1, DIFF_PERIOD, _('Total overtimes/undertimes ({})').format(date.today().strftime('%d.%m.%Y')), header_format)
    months = data['months']
    NORM_STATS_START = SPACE + 1
    FACT_STATS_START = _generate_months_stat(worksheet, NORM_STATS_START, months, _('The norm of hours'), header_format)
    DIFF_STATS_START = _generate_months_stat(worksheet, FACT_STATS_START, months, _('Hours worked'), header_format)
    DIFF_CELEBRATES_STATS_START = _generate_months_stat(worksheet, DIFF_STATS_START, months,  _('Total overtimes/undertimes'), header_format)
    PLAN_STATS_START = _generate_months_stat(worksheet, DIFF_CELEBRATES_STATS_START, months, _('Overtimes/undertimes in celebrations'), header_format)
    _generate_months_stat(worksheet, PLAN_STATS_START, months, _('Planned work hours'), header_format)
    worksheet.set_column(FIO, FIO, 20)
    worksheet.set_column(TABEL_CODE, TABEL_CODE, 15)
    worksheet.set_column(NORM_PERIOD, NORM_PERIOD, 15)
    worksheet.set_column(FACT_PERIOD, FACT_PERIOD, 15)
    worksheet.set_column(DIFF_PERIOD, DIFF_PERIOD, 25)
    worksheet.set_row(0, 50)
    row = 2
    employees = data['employees']
    data = data['data']
    for employee in employees:
        worksheet.write_string(row, FIO, employee.user.get_fio(), def_format)
        worksheet.write_string(row, TABEL_CODE, employee.tabel_code or '', def_format)
        worksheet.write_string(row, NORM_PERIOD, str(data.get(employee.id, {}).get('norm_sum', 0)), def_format)
        worksheet.write_string(row, FACT_PERIOD, str(data.get(employee.id, {}).get('fact_sum', 0)), def_format)
        worksheet.write_string(row, DIFF_PERIOD, str(data.get(employee.id, {}).get('fact_sum', 0) - data.get(employee.id, {}).get('norm_sum', 0)), def_format)
        _fill_month_stat(worksheet, NORM_STATS_START, row, months, lambda month: data.get(employee.id, {}).get(month, {}).get('norm', 0), def_format)
        _fill_month_stat(worksheet, FACT_STATS_START, row, months, lambda month: data.get(employee.id, {}).get(month, {}).get('fact', 0), def_format)
        _fill_month_stat(
            worksheet, 
            DIFF_STATS_START, 
            row, 
            months, 
            lambda month: data.get(employee.id, {}).get(month, {}).get('fact', 0) - data.get(employee.id, {}).get(month, {}).get('norm', 0), 
            def_format,
        )
        _fill_month_stat(
            worksheet, 
            DIFF_CELEBRATES_STATS_START, 
            row, 
            months, 
            lambda month: data.get(employee.id, {}).get(month, {}).get('fact_celebration', 0) - data.get(employee.id, {}).get(month, {}).get('norm_celebration', 0), 
            def_format,
        )
        _fill_month_stat(worksheet, PLAN_STATS_START, row, months, lambda month: data.get(employee.id, {}).get(month, {}).get('plan', 0), def_format)
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
