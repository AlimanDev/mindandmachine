from django.db.models import Q
from src.reports.registry import BaseRegisteredReport

from datetime import date, timedelta, datetime


URV_STAT = 'urv_stat'
URV_STAT_TODAY = 'urv_stat_today'
URV_VIOLATORS_REPORT = 'urv_violators_report'
URV_STAT_V2 = 'urv_stat_v2'
UNACCOUNTED_OVERTIME = 'unaccounted_overtime'
OVERTIMES_UNDERTIMES = 'overtimes_undertimes'
PIVOT_TABEL = 'pivot_tabel'
SCHEDULE_DEVATION = 'schedule_devation'


class DatesReportMixin:
    @staticmethod
    def get_dates(context):
        dt_from = context.get('dt_from')
        dt_to = context.get('dt_to')
        if not dt_from or not dt_to:
            dt_from = dt_to = date.today() - timedelta(1)
        elif isinstance(dt_from, str):
            dt_from = datetime.strptime(dt_from, '%Y-%m-%d').date()
            dt_to = datetime.strptime(dt_to, '%Y-%m-%d').date()
        return dt_from, dt_to


class UrvStatReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по УРВ'
    code = URV_STAT

    def get_file(self):
        from src.reports.utils.create_urv_stat import urv_stat_v1
        dt_from, dt_to = self.get_dates(self.context)
        title = f'URV_{dt_from}-{dt_to}.xlsx'
        return urv_stat_v1(dt_from, dt_to, title=title, shop_ids=self.context.get('shop_ids', []), network_id=self.network_id, in_memory=True)
        

class UrvStatTodayReport(BaseRegisteredReport):
    name = 'Отчет по УРВ за сегодняшний день'
    code = URV_STAT_TODAY

    def get_file(self):
        from src.reports.utils.create_urv_stat import urv_stat_v1
        dt = date.today()
        title = f'URV_today_{dt}.xlsx'

        return urv_stat_v1(dt, dt, title=title, shop_ids=self.context.get('shop_ids', []), network_id=self.network_id, comming_only=True, in_memory=True)

class UrvViolatorsReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по нарушителям УРВ'
    code = URV_VIOLATORS_REPORT

    def get_file(self):
        from src.reports.utils.urv_violators import urv_violators_report_xlsx
        dt_from, dt_to = self.get_dates(self.context)

        return urv_violators_report_xlsx(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []), in_memory=True)

    def get_recipients_shops(self):
        from src.reports.utils.urv_violators import urv_violators_report
        dt_from, dt_to = self.get_dates(self.context)
        data = urv_violators_report(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []))
        shop_ids = []
        for d in data.values():
            shop_ids += list(set(map(lambda x: x['shop_id'], d.values())))

        return set(shop_ids)


class UrvStatV2Report(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по УРВ версия 2'
    code = URV_STAT_V2

    def get_file(self):
        from src.reports.utils.create_urv_stat import urv_stat_v2
        dt_from, dt_to = self.get_dates(self.context)
        title = f'URV_users_{dt_from}-{dt_to}.xlsx'

        return urv_stat_v2(dt_from, dt_to, title=title, network_id=self.network_id, shop_ids=self.context.get('shop_ids', []), in_memory=True)
    
    def get_recipients_shops(self):
        from src.timetable.models import AttendanceRecords
        dt_from, dt_to = self.get_dates(self.context)
        shop_filter = {}
        if self.context.get('shop_ids', []):
            shop_filter['shop_id__in'] = self.context.get('shop_ids', [])
        return set(AttendanceRecords.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            shop__network_id=self.network_id,
            **shop_filter,
        ).values_list('shop_id', flat=True))

class UnaccountedOvertivmeReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по неучтенным переработкам'
    code = UNACCOUNTED_OVERTIME

    def get_file(self):
        from src.reports.utils.unaccounted_overtime import unaccounted_overtimes_xlsx
        dt_from, dt_to = self.get_dates(self.context)
        return unaccounted_overtimes_xlsx(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []), in_memory=True)

    def get_recipients_shops(self):
        from src.reports.utils.unaccounted_overtime import get_unaccounted_overtimes
        dt_from, dt_to = self.get_dates(self.context)

        return set(get_unaccounted_overtimes(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', [])).values_list('shop_id', flat=True))

class UndertimesOvertimesReport(BaseRegisteredReport):
    name = 'Отчет по переработкам/недоработкам'
    code = OVERTIMES_UNDERTIMES

    def get_file(self):
        from src.reports.utils.overtimes_undertimes import overtimes_undertimes_xlsx
        return overtimes_undertimes_xlsx(period_step=self.context.get('period_step', 6), shop_ids=self.context.get('shop_ids', []), in_memory=True)


class PivotTabelReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Сводный табель'
    code = PIVOT_TABEL

    def get_file(self):
        from src.reports.utils.pivot_tabel import PlanAndFactPivotTabel
        dt_from, dt_to = self.get_dates(self.context)
        title = f'Pivot_tabel_{dt_from}-{dt_to}.xlsx'
        pt = PlanAndFactPivotTabel()
        shop_filter = {}
        if self.context.get('shop_ids'):
            shop_filter['shop_id__in'] = self.context.get('shop_ids')
        return {
            'name': title,
            'file': pt.get_pivot_file(dt__gte=dt_from, dt__lte=dt_to, shop__network_id=self.network_id, **shop_filter),
            'type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }

class ScheduleDevationReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по отклонениям от планового графика'
    code = SCHEDULE_DEVATION

    def get_file(self):
        from src.reports.utils.schedule_deviation import schedule_deviation_report
        dt_from, dt_to = self.get_dates(self.context)
        title = f'Scedule_deviation_{dt_from}-{dt_to}.xlsx'
        return schedule_deviation_report(dt_from, dt_to, title, in_memory=True, shop_ids=self.context.get('shop_ids'))

    def get_recipients_shops(self):
        from src.timetable.models import PlanAndFactHours
        dt_from, dt_to = self.get_dates(self.context)
        data = PlanAndFactHours.objects.filter(Q(fact_work_hours__gt=0) | Q(plan_work_hours__gt=0), dt__gte=dt_from, dt__lte=dt_to)
        if self.context.get('shop_ids', []):
            data = data.filter(shop_id__in=self.context.get('shop_ids', []))
        
        return set(data.values_list('shop_id', flat=True))
