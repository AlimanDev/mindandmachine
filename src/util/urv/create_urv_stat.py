from src.timetable.models import AttendanceRecords, WorkerDay
from src.base.models import Shop
import xlsxwriter
import io
import datetime
from src.timetable.utils import wd_stat_count
from django.db.models import Sum

COLOR_GREEN = '#00FF00'
COLOR_RED = '#FF0000'
COLOR_YELLOW = '#FFFF00'
COLOR_HEADER = '#CBF2E0'
#FIXME wd_stat_count не совсем правильная функция, заменить на более актуальную
def main(dt_from, dt_to, title=None, shop_codes=None, shop_level=2, comming_only=False, network_id=None):
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

    workbook = xlsxwriter.Workbook(f'URV_stat_{dt_from}_{dt_to}.xlsx' if not title else title)
    worksheet = workbook.add_worksheet('{}-{}'.format(dt_from.strftime('%Y.%m.%d'), dt_to.strftime('%Y.%m.%d')))
    shops = Shop.objects.filter(level__gte=shop_level).filter(dttm_deleted__isnull=True, network_id=network_id)
    if shop_codes:
        shops = shops.filter(code__in=shop_codes)
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
        for date in dates:
            worker_days = WorkerDay.objects.filter(
                shop=shop, 
                type=WorkerDay.TYPE_WORKDAY, 
                dt=date,
                employment__dt_fired__isnull=True,
                is_fact=True,
            )
            wd_count = worker_days.count()
            if not comming_only:
                wd_hours = wd_stat_count(worker_days, shop).aggregate(
                    hours_count_fact=Sum('hours_fact'),
                    hours_count_plan=Sum('hours_plan'),
                )
                leaving_count = AttendanceRecords.objects.filter(shop=shop, dttm__date=date, type=AttendanceRecords.TYPE_LEAVING).distinct('user').count()
            coming_count = AttendanceRecords.objects.filter(shop=shop, dttm__date=date, type=AttendanceRecords.TYPE_COMING).distinct('user').count()
            worksheet.write_string(row, DATE, date.strftime('%d.%m.%Y'), workbook.add_format(def_format))
            worksheet.write_string(row, PLAN_COMMING, str(wd_count), workbook.add_format(def_format))
            worksheet.write_string(row, FACT_COMMING, str(coming_count), workbook.add_format(def_format))
            worksheet.write_string(row, DIFF_COMMING, str(wd_count - coming_count), workbook.add_format(def_format))
            if not comming_only:
                worksheet.write_string(row, PLAN_LEAVING, str(wd_count), workbook.add_format(def_format))
                worksheet.write_string(row, FACT_LEAVING, str(leaving_count), workbook.add_format(def_format))
                worksheet.write_string(row, DIFF_LEAVING, str(wd_count - leaving_count), workbook.add_format(def_format))
                worksheet.write_string(row, PLAN_HOURS, str(wd_hours['hours_count_plan']), workbook.add_format(def_format))
                worksheet.write_string(row, FACT_HOURS, str(wd_hours['hours_count_fact']), workbook.add_format(def_format))
                worksheet.write_string(row, DIFF_HOURS, str((wd_hours['hours_count_plan'] or 0) - (wd_hours['hours_count_fact'] or 0)), workbook.add_format(def_format))


            row += 1
    workbook.close()