from datetime import date, timedelta, datetime
from copy import deepcopy
from unittest.mock import Mock

from django.db.models import Q, Prefetch, Case, When, Value, F, Exists, OuterRef, QuerySet
from django.utils.translation import gettext as _

from django.utils.functional import cached_property

from src.apps.base.models import Network
from src.apps.recognition.models import Tick, TickPhoto
from src.apps.timetable.models import WorkerDay
from src.apps.reports.registry import BaseRegisteredReport
from src.apps.reports.utils.schedule_deviation import schedule_deviation_report
from src.common.dg.ticks_report import BaseTicksReportGenerator, TicksOdsReportGenerator, TicksOdtReportGenerator, TicksJsonReportGenerator


URV_STAT = 'urv_stat'
URV_STAT_TODAY = 'urv_stat_today'
URV_VIOLATORS_REPORT = 'urv_violators_report'
URV_STAT_V2 = 'urv_stat_v2'
UNACCOUNTED_OVERTIME = 'unaccounted_overtime'
OVERTIMES_UNDERTIMES = 'overtimes_undertimes'
PIVOT_TABEL = 'pivot_tabel'
SCHEDULE_DEVIATION = 'schedule_deviation'
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
        from src.apps.reports.utils.create_urv_stat import urv_stat_v1
        dt_from, dt_to = self.get_dates(self.context)
        title = f'URV_{dt_from}-{dt_to}.xlsx'
        return urv_stat_v1(dt_from, dt_to, title=title, shop_ids=self.context.get('shop_ids', []), network_id=self.network_id, in_memory=True)
        

class UrvStatTodayReport(BaseRegisteredReport):
    name = 'Отчет по УРВ за сегодняшний день'
    code = URV_STAT_TODAY

    def get_file(self):
        from src.apps.reports.utils.create_urv_stat import urv_stat_v1
        dt = date.today()
        title = f'URV_today_{dt}.xlsx'

        return urv_stat_v1(dt, dt, title=title, shop_ids=self.context.get('shop_ids', []), network_id=self.network_id, comming_only=True, in_memory=True)


class UrvViolatorsReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по нарушителям УРВ'
    code = URV_VIOLATORS_REPORT

    def get_file(self):
        from src.apps.reports.utils.urv_violators import urv_violators_report_xlsx
        dt_from, dt_to = self.get_dates(self.context)

        return urv_violators_report_xlsx(network_id=self.network_id, dt_from=dt_from, dt_to=dt_to, in_memory=True, data=self.report_data)

    @cached_property
    def report_data(self):
        from src.apps.reports.utils.urv_violators import urv_violators_report
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
        from src.apps.reports.utils.create_urv_stat import urv_stat_v2
        dt_from, dt_to = self.get_dates(self.context)
        title = f'URV_users_{dt_from}-{dt_to}.xlsx'

        return urv_stat_v2(dt_from, dt_to, title=title, network_id=self.network_id, shop_ids=self.context.get('shop_ids', []), in_memory=True)

    def get_recipients_shops(self):
        from src.apps.timetable.models import AttendanceRecords
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


class UnaccountedOvertimeReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по неучтенным переработкам'
    code = UNACCOUNTED_OVERTIME

    def get_file(self):
        from src.apps.reports.utils.unaccounted_overtime import unaccounted_overtimes_xlsx
        dt_from, dt_to = self.get_dates(self.context)
        return unaccounted_overtimes_xlsx(network_id=self.network_id, dt_from=dt_from, dt_to=dt_to, in_memory=True, data=self.report_data)

    @cached_property
    def report_data(self):
        from src.apps.reports.utils.unaccounted_overtime import get_unaccounted_overtimes
        dt_from, dt_to = self.get_dates(self.context)
        return get_unaccounted_overtimes(self.network_id, dt_from=dt_from, dt_to=dt_to, shop_ids=self.context.get('shop_ids', []))

    def get_recipients_shops(self):
        return set(self.report_data.values_list('shop_id', flat=True))


class UndertimesOvertimesReport(BaseRegisteredReport):
    name = 'Отчет по переработкам/недоработкам'
    code = OVERTIMES_UNDERTIMES

    def get_file(self):
        from src.apps.reports.utils.overtimes_undertimes import overtimes_undertimes_xlsx
        return overtimes_undertimes_xlsx(period_step=self.context.get('period_step', 6), shop_ids=self.context.get('shop_ids', []), in_memory=True)


class PivotTabelReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Сводный табель'
    code = PIVOT_TABEL

    def get_file(self):
        from src.apps.reports.utils.pivot_tabel import PlanAndFactPivotTabel
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


class ScheduleDeviationReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчет по отклонениям от планового графика'
    code = SCHEDULE_DEVIATION

    def get_file(self) -> dict:
        dt_from, dt_to = self.get_dates(self.context)
        report = schedule_deviation_report(
            dt_from,
            dt_to,
            created_by_id=self.context.get('created_by_id'),
            shop_ids=self.context.get('shop_id__in'),
            filters=self.context.get('filters')
        )
        return {
            'name': f'Schedule_deviation_{dt_from}-{dt_to}.xlsx',
            'file': report,
            'type': f'application/xlsx'
        }

    def get_recipients_shops(self):
        from src.apps.timetable.models import PlanAndFactHours
        dt_from, dt_to = self.get_dates(self.context)
        data = PlanAndFactHours.objects.filter(Q(fact_work_hours__gt=0) | Q(plan_work_hours__gt=0), dt__gte=dt_from, dt__lte=dt_to)
        if self.context.get('shop_id__in', []):
            data = data.filter(shop_id__in=self.context.get('shop_id__in', []))
        
        return set(data.values_list('shop_id', flat=True))


class TickReport(BaseRegisteredReport, DatesReportMixin):
    name = 'Отчёт об отметках сотрудников'
    code = TICK
    generators = {
        'docx': TicksOdtReportGenerator,
        'xlsx': TicksOdsReportGenerator,
        'json': TicksJsonReportGenerator
    }

    def __init__(self, network_id: int, context: dict, qs: QuerySet = None, *args, **kwargs):
        self.qs = qs
        self.dt_from, self.dt_to = self.get_dates(context)
        super().__init__(network_id, context, *args, **kwargs)

    def get_file(self) -> dict:
        Generator: BaseTicksReportGenerator = self.generators[self.format]
        report = Generator(
            ticks=self.report_data,
            dt_from=self.dt_from,
            dt_to=self.dt_to
        ).generate_report()
        return {
            'name': f'tick_report_{self.dt_from}_{self.dt_to}{self.shops_suffix}.{self.format}',
            'file': report,
            'type': f'application/{self.format}'
        }

    @cached_property
    def format(self) -> str:
        with_biometrics = self.context.get('with_biometrics')
        _format = self.context.get('format', 'docx' if with_biometrics else 'xlsx')
        assert _format != 'docx' or with_biometrics  # don't render docx without photos
        return _format

    @cached_property
    def report_data(self) -> list:
        """
        Autoticks + manual ticks. Checked against plan for violations, liveness_str attribute for Word/ODT format, 
        sorted by fio (full name) and dttm.
        """
        all_ticks: list[Tick] = self._get_ticks()
        plan_wdays = self._get_plan_wdays()
        if not self.qs:
            all_ticks += self._get_wdays()
        for tick in all_ticks:
            tick.liveness_str = f'{int(tick.min_liveness_prop * 100)}%' if tick.min_liveness_prop else None # to percentage (%)
            tick.violation = None
            # Multiple WorkerDays can be in one day
            plans = tuple(filter(lambda wd: wd.employee_id == tick.employee_id and wd.dt == tick.dttm.date(), plan_wdays))
            if not plans:
                tick.violation = _('Arrival without plan')
            else:
                if len(plans) == 1:     # One plan found
                    plan = plans[0]
                else:                   # Multiple plans found, choosing the closest one
                    plan = self._choose_closest_plan(plans, tick)
                    if tick.tick_kind == _('Manual tick'):
                        self._manual_tick_to_auto(plan, plans, tick)

                if tick.type_display == _('Coming') and plan.dttm_work_start:
                    if tick.dttm - plan.dttm_work_start > self.network.allowed_interval_for_late_arrival:
                        tick.violation = _('Late arrival')
                elif tick.type_display == _('Leaving') and plan.dttm_work_end:
                    if plan.dttm_work_end - tick.dttm > self.network.allowed_interval_for_early_departure:
                        tick.violation = _('Early departure')
                    elif tick.dttm - plan.dttm_work_end > self.network.allowed_interval_for_late_departure:
                        tick.violation = _('Late departure')

        all_ticks.sort(key=lambda tick: (tick.user.fio, tick.dttm))
        return all_ticks

    def _get_ticks(self) -> list:
        """Normal Ticks (Autoticks)"""
        qs: QuerySet
        if self.qs:  # Если предоставлен qs, то нам не нужно фильтровать по датам
            qs = self.qs
        else:
            qs = Tick.objects.filter(dttm__gte=self.dt_from, dttm__lt=self.dt_to + timedelta(1))
        qs = qs.filter(
            employee__isnull=False
        ).annotate(
            outsource_network=Case(When(~Q(user__network=F('tick_point__shop__network')), then=F('user__network__name'))),
            tick_kind=Value(_('Autotick')),
            shop_name=F('tick_point__shop__name'),
        ).select_related(
            'user', 'employee__user'
        )
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
        if self.format == 'json':
            qs = qs.select_related('tick_point__shop')
        return list(qs)

    def _get_wdays(self) -> list:
        """"Manual" ticks, from WorkerDay model. When there is no Tick, but the WorkerDay is created by hand."""
        qs = WorkerDay.objects.filter(
            dt__range=(self.dt_from, self.dt_to),
            is_approved=True,
            is_fact=True,
            type__is_dayoff=False,
            employee__isnull=False
        ).annotate(
            tick_coming=Exists(
                Tick.objects.filter(
                dttm=OuterRef('dttm_work_start'),
                employee=OuterRef('employee'),
                tick_point__shop=OuterRef('shop'),
                type=Tick.TYPE_COMING
                )
            ),
            tick_leaving=Exists(
                Tick.objects.filter(
                dttm=OuterRef('dttm_work_end'),
                employee=OuterRef('employee'),
                tick_point__shop=OuterRef('shop'),
                type=Tick.TYPE_LEAVING
                )
            ),
            outsource_network=Case(When(~Q(employee__user__network=F('shop__network')), then=F('employee__user__network__name'))),
            tick_kind=Value(_('Manual tick')),
            shop_name=F('shop__name'),
        ).exclude(
            tick_coming=True,
            tick_leaving=True
        ).select_related(
            'employee__user'
        )
        if shops := self.context.get('shop_id__in'):
            qs = qs.filter(shop_id__in=shops)
        if employees := self.context.get('employee_id__in'):
            qs = qs.filter(employee_id__in=employees)
        if self.format == 'json':
            qs = qs.select_related('shop')

        # Imitating some of the Tick fields
        wdays = []
        for wd in qs:
            wd.tick_point = Mock()
            wd.tick_point.shop = wd.shop
            wd.min_liveness_prop = None
            wd.user = wd.employee.user
            if not wd.tick_coming and wd.dttm_work_start:
                wd.type_display = _('Coming')
                wd.dttm = wd.dttm_work_start
                wdays.append(wd)
            if not wd.tick_leaving and wd.dttm_work_end:
                wd2 = deepcopy(wd)
                wd2.dttm = wd2.dttm_work_end
                wd2.type_display = _('Leaving')
                wdays.append(wd2)
        return  wdays

    def _get_plan_wdays(self) -> tuple:
        """
        Approved plan WorkerDays to check Ticks for violations.
        """
        qs = WorkerDay.objects.filter(
            is_approved=True,
            is_fact=False,
            type__is_dayoff=False
        )
        if self.qs:  # Если предоставлен qs в класс, то нужны планы на конкретные дни
            dts = [tick.dttm.date() for tick in self.qs]
            ids = [tick.employee_id for tick in self.qs]
            qs = qs.filter(dt__in=dts, employee_id__in=ids)
        else:
            qs = qs.filter(dt__range=(self.dt_from, self.dt_to))

        if shops := self.context.get('shop_id__in'):
            qs = qs.filter(shop_id__in=shops)
        if employees := self.context.get('employee_id__in'):
            qs = qs.filter(employee_id__in=employees)
        return tuple(qs)

    @staticmethod
    def _choose_closest_plan(plans: tuple[WorkerDay], tick: Tick) -> WorkerDay:
        """Returns WorkerDay whose dttm_work_start/dttm_work_end (depending on tick.type_display) is closest to tick.dttm"""
        assert len(plans) > 1
        dttm_attr = 'dttm_work_start' if tick.type_display == _('Coming') else 'dttm_work_end'
        closest_plan = plans[0]
        for wd in plans[1:]:
            dttm_closest_plan = getattr(closest_plan, dttm_attr, None)
            dttm_wd = getattr(wd, dttm_attr, None)
            if dttm_wd and (
                not dttm_closest_plan or                                    # wd has dttm, but previous plan doesn't
                abs(tick.dttm - dttm_wd) < abs(tick.dttm - dttm_closest_plan)    # wd.dttm_work_... is closer to tick than previous plan's
                ):
                closest_plan = wd
        return closest_plan

    @staticmethod
    def _manual_tick_to_auto(closet_plan: WorkerDay, plans: tuple[WorkerDay], tick: Tick):
        """
        Multiple plan WorkerDays (back-to-back, with `dttm_work_end==dttm_work_start`)
        may have only 2 fact Ticks (1 for arrival and 1 for departure).
        The rest of fact WorkerDays in between should be considered 'autoticks', and not 'manual' as usual.
        """
        if tick.type_display == _('Coming'):
            closest_plan_attr = 'dttm_work_start'
            plans_attr = 'dttm_work_end'
        else:
            closest_plan_attr = 'dttm_work_end'
            plans_attr = 'dttm_work_start'
        if any(map(
            lambda wd: closet_plan.id != wd.id and \
            getattr(wd, plans_attr) == getattr(closet_plan, closest_plan_attr)
        , plans)):
            tick.tick_kind=_('Autotick')


    @cached_property
    def network(self) -> Network:
        return Network.objects.get(id=self.network_id)

    @property
    def shops_suffix(self) -> str:
        shops = self.context.get('shop_id__in', [])
        shops = map(lambda id: str(id), shops)
        return f'({", ".join(shops)})'
