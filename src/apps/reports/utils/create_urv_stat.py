from src.apps.timetable.models import AttendanceRecords, WorkerDay, PlanAndFactHours
from src.apps.base.models import Network, Shop, Employment
import xlsxwriter
import io
import datetime
from django.db.models import Sum, Q


COLOR_GREEN = '#00FF00'
COLOR_RED = '#fc6c58'
COLOR_YELLOW = '#FFFF00'
COLOR_HEADER = '#CBF2E0'

RECORD_TYPES = {
    AttendanceRecords.TYPE_COMING: 'Приход',
    AttendanceRecords.TYPE_LEAVING: 'Уход',
}


def urv_stat_v1(dt_from, dt_to, title=None, shop_codes=None, shop_ids=None, comming_only=False, network_id=None, in_memory=False):
    SHOP = 0
    DATE = 1
    shift = 0
    if not comming_only:
        shift = 2
        LATE = 2
        EARLY = 3
    PLAN_COMMING = 2 + shift
    FACT_COMMING = 3 + shift
    DIFF_COMMING = 4 + shift
    PLAN_LEAVING = 5 + shift
    FACT_LEAVING = 6 + shift
    DIFF_LEAVING = 7 + shift
    PLAN_HOURS = 8 + shift
    FACT_HOURS = 9 + shift
    DIFF_HOURS = 10 + shift
    DIFF_HOURS_PERCENT = 11 + shift

    shop_name_form = {}
    if network_id:
        network = Network.objects.get(id=network_id)
        shop_name_form = network.settings_values_prop.get('shop_name_form', {})

    shops = Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=dt_to),
        id__in=WorkerDay.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            shop__network_id=network_id,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=True,
            is_fact=False,
        ).values_list('shop_id', flat=True),
    )

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(f'URV_stat_{dt_from}_{dt_to}.xlsx' if not title else title)
    worksheet = workbook.add_worksheet('{}-{}'.format(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d')))
    if shop_codes:
        shops = shops.filter(code__in=shop_codes)
    if shop_ids:
        shops = shops.filter(id__in=shop_ids)
    dates = [dt_from + datetime.timedelta(days=i) for i in range((dt_to -  dt_from).days + 1)]
    def_dict_format = {
        'border': 1,
        'valign': 'vcenter',
        'align': 'center',
        'text_wrap': True,
    }
    red_format_dict = def_dict_format.copy()
    red_format_dict['bg_color'] = COLOR_RED
    def_format = workbook.add_format(def_dict_format)
    red_format = workbook.add_format(red_format_dict)
    header_format = workbook.add_format({
        'border': 1,
        'bold': True,
        'text_wrap': True,
        'valign': 'vcenter',
        'align': 'center',
    })
    worksheet.write_string(0, SHOP, shop_name_form.get('singular', {}).get('I', 'магазин').capitalize(), header_format)
    worksheet.set_column(SHOP, SHOP, 12)
    worksheet.write_string(0, DATE, 'Дата', header_format)
    worksheet.write_string(0, PLAN_COMMING, 'Кол-во отметок план, ПРИХОД', header_format)
    worksheet.set_column(DATE, DATE, 10)
    worksheet.set_column(PLAN_COMMING, PLAN_COMMING, 10)
    worksheet.write_string(0, FACT_COMMING, 'Кол-во отметок факт, ПРИХОД', header_format)
    worksheet.set_column(FACT_COMMING, FACT_COMMING, 10)
    worksheet.write_string(0, DIFF_COMMING, 'Разница, ПРИХОД', header_format)
    worksheet.set_column(DIFF_COMMING, DIFF_COMMING, 10)
    if not comming_only:
        worksheet.write_string(0, LATE, 'Опоздания', header_format)
        worksheet.write_string(0, EARLY, 'Ранний уход', header_format)
        worksheet.set_column(LATE, LATE, 10)
        worksheet.set_column(EARLY, EARLY, 10)
        worksheet.write_string(0, PLAN_LEAVING, 'Кол-во отметок план, УХОД', header_format)
        worksheet.set_column(PLAN_LEAVING, PLAN_LEAVING, 10)
        worksheet.write_string(0, FACT_LEAVING, 'Кол-во отметок факт, УХОД', header_format)
        worksheet.set_column(FACT_LEAVING, FACT_LEAVING, 10)
        worksheet.write_string(0, DIFF_LEAVING, 'Разница, УХОД', header_format)
        worksheet.set_column(DIFF_LEAVING, DIFF_LEAVING, 10)
        worksheet.write_string(0, PLAN_HOURS, 'Кол-во часов план', header_format)
        worksheet.set_column(PLAN_HOURS, PLAN_HOURS, 10)
        worksheet.write_string(0, FACT_HOURS, 'Кол-во часов факт', header_format)
        worksheet.set_column(FACT_HOURS, FACT_HOURS, 10)
        worksheet.write_string(0, DIFF_HOURS, 'Разница, ЧАСЫ', header_format)
        worksheet.set_column(DIFF_HOURS, DIFF_HOURS, 10)
        worksheet.write_string(0, DIFF_HOURS_PERCENT, 'Разница, ПРОЦЕНТЫ', header_format)
        worksheet.set_column(DIFF_HOURS_PERCENT, DIFF_HOURS_PERCENT, 10)
    row = 1
    for shop in shops:
        for date in dates:
            employee_ids = list(Employment.objects.get_active(shop.network_id, dt_from=date, dt_to=date).values_list('employee_id', flat=True))
            worksheet.write_string(row, SHOP, shop.name, def_format)
            worker_days_stat = PlanAndFactHours.objects.filter(
                shop=shop, 
                dt=date,
                employee_id__in=employee_ids,
                wd_type_id=WorkerDay.TYPE_WORKDAY,
            ).aggregate(
                plan_ticks=Sum('ticks_plan_count'),
                fact_comming_ticks=Sum('ticks_comming_fact_count'),
                fact_leaving_ticks=Sum('ticks_leaving_fact_count'),
                lates=Sum('late_arrival_count'),
                earlies=Sum('early_departure_count'),
                hours_count_plan=Sum('plan_work_hours'),
                hours_count_fact=Sum('fact_work_hours'),
            )
            wd_count = worker_days_stat['plan_ticks'] // 2
            worksheet.write_string(row, DATE, date.strftime('%d.%m.%Y'), def_format)
            if not comming_only:
                worksheet.write_string(row, LATE, str(worker_days_stat['lates'] or 0), def_format)
                worksheet.write_string(row, EARLY, str(worker_days_stat['earlies'] or 0), def_format)
            worksheet.write_string(row, PLAN_COMMING, str(wd_count), def_format)
            worksheet.write_string(row, FACT_COMMING, str(worker_days_stat['fact_comming_ticks']), def_format)
            worksheet.write_string(row, DIFF_COMMING, str(wd_count - worker_days_stat['fact_comming_ticks']), def_format if wd_count - worker_days_stat['fact_comming_ticks'] == 0 else red_format)
            if not comming_only:
                plan_hours = datetime.timedelta(seconds=int(worker_days_stat['hours_count_plan'] * 60 * 60)) or datetime.timedelta(0)
                fact_hours = datetime.timedelta(seconds=int(worker_days_stat['hours_count_fact'] * 60 * 60)) or datetime.timedelta(0)
                def get_str_timedelta(tm):
                    c = 1
                    if tm.days < 0:
                        c = -1
                    hours = int(tm.total_seconds() / 3600)
                    minutes = int((tm.total_seconds() - hours * 3600) / 60)
                    seconds = int(tm.total_seconds() - hours * 3600 - minutes * 60)
                    return f'{hours:02}:{c * minutes:02}:{c * seconds:02}'
                worksheet.write_string(row, PLAN_LEAVING, str(wd_count), def_format)
                worksheet.write_string(row, FACT_LEAVING, str(worker_days_stat['fact_leaving_ticks']), def_format)
                worksheet.write_string(row, DIFF_LEAVING, str(wd_count - worker_days_stat['fact_leaving_ticks']), def_format if wd_count - worker_days_stat['fact_leaving_ticks'] == 0 else red_format)
                worksheet.write_string(row, PLAN_HOURS, get_str_timedelta(plan_hours), def_format)
                worksheet.write_string(row, FACT_HOURS, get_str_timedelta(fact_hours), def_format)
                worksheet.write_string(row, DIFF_HOURS, get_str_timedelta(plan_hours - fact_hours), def_format)
                percent_diff = round(fact_hours / (plan_hours or datetime.timedelta(seconds=1)) * 100)
                worksheet.write_string(
                    row, 
                    DIFF_HOURS_PERCENT, 
                    str(percent_diff) + '%', 
                    def_format if percent_diff >= 100 and percent_diff != 0 else red_format,
                )

            row += 1
    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': f'URV_stat_{dt_from}_{dt_to}.xlsx' if not title else title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }


def urv_stat_v2(dt_from, dt_to, title=None, shop_ids=None, network_id=None, in_memory=False):
    DTTM = 0
    SHOP_CODE = 1
    SHOP = 2
    USER = 3
    USER_CODE = 4
    TYPE = 5

    if in_memory:
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    else:
        workbook = xlsxwriter.Workbook(f'URV_users_stat_{dt_from}_{dt_to}.xlsx' if not title else title)
    worksheet = workbook.add_worksheet('{}-{}'.format(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d')))
   
    def_format = {
        'border': 1,
        'bold': True,
        'text_wrap': True,
        'valign': 'top',
    }
    shop_name_form = {}
    if network_id:
        network = Network.objects.get(id=network_id)
        shop_name_form = network.settings_values_prop.get('shop_name_form', {})
    worksheet.write_string(0, SHOP_CODE, f"Код {shop_name_form.get('singular', {}).get('R', 'магазина')}", workbook.add_format(def_format))
    worksheet.set_column(SHOP_CODE, SHOP_CODE, 12)
    worksheet.write_string(0, SHOP, shop_name_form.get('singular', {}).get('I', 'магазин').capitalize(), workbook.add_format(def_format))
    worksheet.set_column(SHOP, SHOP, 25)
    worksheet.write_string(0, DTTM, 'Время события', workbook.add_format(def_format))
    worksheet.set_column(DTTM, DTTM, 20)
    worksheet.write_string(0, USER_CODE, 'Табельный номер сотрудника', workbook.add_format(def_format))
    worksheet.set_column(USER_CODE, USER_CODE, 12)
    worksheet.write_string(0, USER, 'ФИО сотрудника', workbook.add_format(def_format))
    worksheet.set_column(USER, USER, 30)
    worksheet.write_string(0, TYPE, 'Тип события', workbook.add_format(def_format))
    worksheet.set_column(TYPE, TYPE, 11)
    
    shop_filter = {}
    if shop_ids:
        shop_filter['shop_id__in'] = shop_ids

    records = AttendanceRecords.objects.select_related(
        'shop',
        'user',
        'employee',
    ).filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        shop__network_id=network_id,
        **shop_filter,
    ).order_by(
        'shop_id',
        'dttm',
    )

    row = 1
    for record in records:
        worksheet.write(row, SHOP_CODE, record.shop.code or 'Без кода')
        worksheet.write(row, SHOP, record.shop.name)
        worksheet.write(row, DTTM, str(record.dttm.replace(microsecond=0)))
        worksheet.write(row, USER_CODE, record.employee.tabel_code or 'Без табельного номера')
        worksheet.write(row, USER, f'{record.user.last_name} {record.user.first_name} {record.user.middle_name or ""}')
        worksheet.write(row, TYPE, RECORD_TYPES.get(record.type, 'Неизвестно'))
        row += 1

    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': f'URV_users_stat_{dt_from}_{dt_to}.xlsx' if not title else title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }
