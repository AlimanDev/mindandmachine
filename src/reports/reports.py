from datetime import date, timedelta, datetime

from django.db.models import Q, Prefetch, QuerySet
from django.utils.functional import cached_property

from src.recognition.models import Tick, TickPhoto
from src.reports.registry import BaseRegisteredReport
from src.util.dg.ticks_report import TicksOdsReportGenerator, TicksOdtReportGenerator


URV_STAT = 'urv_stat'
URV_STAT_TODAY = 'urv_stat_today'
URV_VIOLATORS_REPORT = 'urv_violators_report'
URV_STAT_V2 = 'urv_stat_v2'
UNACCOUNTED_OVERTIME = 'unaccounted_overtime'
OVERTIMES_UNDERTIMES = 'overtimes_undertimes'
PIVOT_TABEL = 'pivot_tabel'
SCHEDULE_DEVATION = 'schedule_devation'
TICK = 'tick'


class DatesReportMixin:
    @staticmethod
    def get_dates(context: dict) -> tuple[date, date]:
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

        return urv_violators_report_xlsx(network_id=self.network_id, dt_from=dt_from, dt_to=dt_to, in_memory=True, data=self.report_data)

    @cached_property
    def report_data(self):
        from src.reports.utils.urv_violators import urv_violators_report
        dt_from, dt_to = self.get_dates(self.context)
        return urv_violators_report(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []))

    def get_recipients_shops(self):
        shop_ids = []
        for d in self.report_data.values():
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
        return unaccounted_overtimes_xlsx(network_id=self.network_id, dt_from=dt_from, dt_to=dt_to, in_memory=True, data=self.report_data)

    @cached_property
    def report_data(self):
        from src.reports.utils.unaccounted_overtime import get_unaccounted_overtimes
        dt_from, dt_to = self.get_dates(self.context)
        return get_unaccounted_overtimes(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []))

    def get_recipients_shops(self):
        return set(self.report_data.values_list('shop_id', flat=True))


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


class TickReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчёт об отметках сотрудников'
    code = TICK

    def __init__(self, network_id: int, context: dict, *args, **kwargs):
        self.dt_from, self.dt_to = self.get_dates(context)
        self.order_by = context.get('order_by', ['user__last_name', 'user__first_name', 'user__middle_name', 'dttm'])
        super().__init__(network_id, context, *args, **kwargs)
    
    def get_file(self) -> dict:
        if self.context.get('with_biometrics'):
            Generator = TicksOdtReportGenerator
            format = 'docx'
        else:
            Generator = TicksOdsReportGenerator
            format = 'xlsx'
        report = Generator(
            ticks_queryset=self.report_data,
            dt_from=self.dt_from,
            dt_to=self.dt_to
        ).generate(convert_to=format)
        return {
            'name': f'tick_report_{self.dt_from}_{self.dt_to}{self.shops_suffix}.{format}',
            'file': report,
            'type': f'application/{format}'
        }

    @cached_property
    def report_data(self) -> QuerySet:
        qs = Tick.objects.filter(
            dttm__gte=self.dt_from,
            dttm__lt=self.dt_to + timedelta(1)
        ).order_by(*self.order_by)
        if shops := self.context.get('shop_id__in'):
            qs = qs.filter(tick_point__shop_id__in=shops)
        if employees := self.context.get('employee_id__in'):
            qs = qs.filter(employee_id__in=employees)
        if self.context.get('with_biometrics'):
            qs = qs.prefetch_related(
                Prefetch(
                    'tickphoto_set',
                    queryset=TickPhoto.objects.all(),
                    to_attr='tickphotos_list',
                )
            )
        return qs

    @property
    def shops_suffix(self) -> str:
        shops = self.context.get('shop_id__in', [])
        shops = map(lambda id: str(id), shops)
        return f'({", ".join(shops)})'
