from src.timetable.models import AttendanceRecords, WorkerDay
from src.base.models import Shop, Employment
import xlsxwriter
import io
import datetime
from django.db.models import Sum, Q

COLOR_GREEN = '#00FF00'
COLOR_RED = '#FF0000'
COLOR_YELLOW = '#FFFF00'
COLOR_HEADER = '#CBF2E0'

RECORD_TYPES = {
    AttendanceRecords.TYPE_COMING: 'Приход',
    AttendanceRecords.TYPE_LEAVING: 'Уход',
}


def urv_stat_v1(dt_from, dt_to, title=None, shop_codes=None, shop_ids=None, comming_only=False, network_id=None, in_memory=False):
    SHOP = 0
    DATE = 1
    PLAN_COMMING = 2
    FACT_COMMING = 3
    DIFF_COMMING = 4
    PLAN_LEAVING = 5
    FACT_LEAVING = 6
    DIFF_LEAVING = 7
    PLAN_HOURS = 8
    FACT_HOURS = 9
    DIFF_HOURS = 10

    shops = Shop.objects.filter(
        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=dt_to),
        id__in=WorkerDay.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            shop__network_id=network_id,
            type=WorkerDay.TYPE_WORKDAY,
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
    def_format = {
        'border': 1,
    }
    worksheet.write(0, SHOP, 'Магазин')
    worksheet.write(0, DATE, 'Дата')
    worksheet.write(0, PLAN_COMMING, 'Плановое кол-во отметок, ПРИХОД')
    worksheet.set_column(0, PLAN_COMMING, 15)
    worksheet.write(0, FACT_COMMING, 'Фактическое кол-во отметок, ПРИХОД')
    worksheet.set_column(0, FACT_COMMING, 20)
    worksheet.write(0, DIFF_COMMING, 'Разница, ПРИХОД')
    worksheet.set_column(0, DIFF_COMMING, 20)
    if not comming_only:
        worksheet.write(0, PLAN_LEAVING, 'Плановое кол-во отметок, УХОД')
        worksheet.set_column(0, PLAN_LEAVING, 20)
        worksheet.write(0, FACT_LEAVING, 'Фактическое кол-во отметок, УХОД')
        worksheet.set_column(0, FACT_LEAVING, 20)
        worksheet.write(0, DIFF_LEAVING, 'Разница, УХОД')
        worksheet.set_column(0, DIFF_LEAVING, 20)
        worksheet.write(0, PLAN_HOURS, 'Плановое кол-во часов')
        worksheet.set_column(0, PLAN_HOURS, 20)
        worksheet.write(0, FACT_HOURS, 'Фактическое кол-во часов')
        worksheet.set_column(0, FACT_HOURS, 20)
        worksheet.write(0, DIFF_HOURS, 'Разница, ЧАСЫ')
        worksheet.set_column(0, DIFF_HOURS, 20)
    row = 1
    for shop in shops:
        worksheet.write(row, SHOP, shop.name)
        user_ids = list(Employment.objects.get_active(shop.network_id, dt_from=dt_from, dt_to=dt_to).values_list('user_id', flat=True))
        for date in dates:
            plan_worker_days = WorkerDay.objects.filter(
                shop=shop, 
                type=WorkerDay.TYPE_WORKDAY, 
                dt=date,
                worker_id__in=user_ids,
                is_approved=True,
                is_fact=False,
            )
            wd_count = plan_worker_days.count()
            if not comming_only:
                wd_hours = WorkerDay.objects.filter(
                    shop=shop,
                    type=WorkerDay.TYPE_WORKDAY,
                    dt=date,
                    worker_id__in=user_ids,
                ).aggregate(
                    hours_count_plan=Sum('work_hours', filter=Q(is_approved=True, is_fact=False)),
                    hours_count_fact=Sum('work_hours', filter=Q(is_fact=True, is_approved=True)),
                )
                leaving_count = AttendanceRecords.objects.filter(shop=shop, dttm__date=date, type=AttendanceRecords.TYPE_LEAVING, user_id__in=user_ids).distinct('user').count()
            coming_count = AttendanceRecords.objects.filter(shop=shop, dttm__date=date, type=AttendanceRecords.TYPE_COMING, user_id__in=user_ids).distinct('user').count()
            worksheet.write_string(row, DATE, date.strftime('%d.%m.%Y'), workbook.add_format(def_format))
            worksheet.write_string(row, PLAN_COMMING, str(wd_count), workbook.add_format(def_format))
            worksheet.write_string(row, FACT_COMMING, str(coming_count), workbook.add_format(def_format))
            worksheet.write_string(row, DIFF_COMMING, str(wd_count - coming_count), workbook.add_format(def_format))
            if not comming_only:
                plan_hours = wd_hours['hours_count_plan'] or datetime.timedelta(0)
                fact_hours = wd_hours['hours_count_fact'] or datetime.timedelta(0)
                def get_str_timedelta(tm):
                    c = 1
                    if tm.days < 0:
                        c = -1
                    hours = int(tm.total_seconds() / 3600)
                    minutes = int((tm.total_seconds() - hours * 3600) / 60)
                    seconds = int(tm.total_seconds() - hours * 3600 - minutes * 60)
                    return f'{hours:02}:{c * minutes:02}:{c * seconds:02}'
                worksheet.write_string(row, PLAN_LEAVING, str(wd_count), workbook.add_format(def_format))
                worksheet.write_string(row, FACT_LEAVING, str(leaving_count), workbook.add_format(def_format))
                worksheet.write_string(row, DIFF_LEAVING, str(wd_count - leaving_count), workbook.add_format(def_format))
                worksheet.write_string(row, PLAN_HOURS, get_str_timedelta(wd_hours['hours_count_plan'] or datetime.timedelta(0)), workbook.add_format(def_format))
                worksheet.write_string(row, FACT_HOURS, get_str_timedelta(wd_hours['hours_count_fact'] or datetime.timedelta(0)), workbook.add_format(def_format))
                worksheet.write_string(row, DIFF_HOURS, get_str_timedelta((wd_hours['hours_count_plan'] or datetime.timedelta(0)) - (wd_hours['hours_count_fact'] or datetime.timedelta(0))), workbook.add_format(def_format))


            row += 1
    workbook.close()
    if in_memory:
        output.seek(0)
        return {
            'name': f'URV_stat_{dt_from}_{dt_to}.xlsx' if not title else title,
            'file': output,
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }


def urv_stat_v2(dt_from, dt_to, title=None, network_id=None, in_memory=False):
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
    worksheet.write_string(0, SHOP_CODE, 'Код магазина', workbook.add_format(def_format))
    worksheet.set_column(SHOP_CODE, SHOP_CODE, 12)
    worksheet.write_string(0, SHOP, 'Магазин', workbook.add_format(def_format))
    worksheet.set_column(SHOP, SHOP, 25)
    worksheet.write_string(0, DTTM, 'Время события', workbook.add_format(def_format))
    worksheet.set_column(DTTM, DTTM, 20)
    worksheet.write_string(0, USER_CODE, 'Табельный номер сотрудника', workbook.add_format(def_format))
    worksheet.set_column(USER_CODE, USER_CODE, 12)
    worksheet.write_string(0, USER, 'ФИО сотрудника', workbook.add_format(def_format))
    worksheet.set_column(USER, USER, 30)
    worksheet.write_string(0, TYPE, 'Тип события', workbook.add_format(def_format))
    worksheet.set_column(TYPE, TYPE, 11)
    
    records = AttendanceRecords.objects.select_related(
        'shop',
        'user',
    ).filter(
        dt__gte=dt_from,
        dt__lte=dt_to,
        shop__network_id=network_id,
    ).order_by(
        'shop_id',
        'dttm',
    )

    employments = {}
    for e in Employment.objects.get_active(network_id, dt_from=dt_from, dt_to=dt_to):
        employments.setdefault(e.user_id, {})[e.shop_id] = e

    row = 1
    for record in records:
        worksheet.write(row, SHOP_CODE, record.shop.code or 'Без кода')
        worksheet.write(row, SHOP, record.shop.name)
        worksheet.write(row, DTTM, str(record.dttm.replace(microsecond=0)))
        worksheet.write(row, USER_CODE, employments.get(record.user_id, {}).get(record.shop_id, Employment()).tabel_code or 'Без табельного номера')
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
