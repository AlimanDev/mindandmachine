import logging
from datetime import timedelta

from django.db import transaction
from django.db.models import (
    Q, F, Count, Sum, Min, Max, Case, When, Value, IntegerField, DateTimeField, FloatField
)
from django.db.models.functions import Extract, Coalesce, Cast

from src.base.models import (
    Employment,
    Break,
)
from src.timetable.models import (
    AttendanceRecords
)
from src.timetable.models import (
    WorkerDay,
)
from src.util.utils import dummy_context_mgr


# deprecated
def wd_stat_count(worker_days, shop):
    # break_triplets = json.loads(shop.settings.break_triplets) if shop.settings else []
    break_triplets = {
        b.id: list(map(lambda x: (x[0] / 60, x[1] / 60, 0), b.breaks))
        for b in Break.objects.filter(network_id=shop.network_id)
    }
    breaktime_plan = Value(0, output_field=FloatField())
    breaktime_fact = Value(0, output_field=FloatField())
    if break_triplets:
        whens = [
            When(
                Q(hours_plan_0__gte=break_triplet[0], hours_plan_0__lte=break_triplet[1]) &
                (Q(employment__position__breaks_id=break_id) | (Q(employment__position__breaks__isnull=True) & Q(
                    employment__shop__settings__breaks_id=break_id))),
                then=break_triplet[2]
            )
            for break_id, breaks in break_triplets.items()
            for break_triplet in breaks
        ]
        breaktime_plan = Case(*whens, output_field=FloatField())
        whens = [
            When(
                Q(hours_fact_0__gte=break_triplet[0], hours_fact_0__lte=break_triplet[1]) &
                (Q(employment__position__breaks_id=break_id) | (Q(employment__position__breaks__isnull=True) & Q(
                    employment__shop__settings__breaks_id=break_id))),
                then=break_triplet[2])
            for break_id, breaks in break_triplets.items()
            for break_triplet in breaks
        ]
        breaktime_fact = Case(*whens, output_field=FloatField())

    return worker_days.filter(
        type=WorkerDay.TYPE_WORKDAY
    ).values('worker_id', 'employment_id', 'dt', 'dttm_work_start', 'dttm_work_end').annotate(
        coming=Min('worker__attendancerecords__dttm', filter=Q(
            worker__attendancerecords__shop=shop,
            worker__attendancerecords__dttm__date=F('dt'),
            worker__attendancerecords__type=AttendanceRecords.TYPE_COMING,
        )),
        leaving=Max('worker__attendancerecords__dttm', filter=Q(
            worker__attendancerecords__shop=shop,
            worker__attendancerecords__dttm__date=F('dt'),
            worker__attendancerecords__type=AttendanceRecords.TYPE_LEAVING)),
        is_late=Case(
            When(coming__gt=F('dttm_work_start') - timedelta(minutes=15), then=1),
            default=Value(0), output_field=IntegerField()),
        hours_plan_0=Cast(Extract(F('dttm_work_end') - F('dttm_work_start'), 'epoch') / 3600, FloatField()),
        hours_fact_0=Cast(
            Extract(
                Coalesce(
                    Case(When(leaving__gt=F('dttm_work_end'), then=F('dttm_work_end')),
                         default=F('leaving'), output_field=DateTimeField())
                    -
                    Case(When(coming__lt=F('dttm_work_start'), then=F('dttm_work_start')),
                         default=F('coming'), output_field=DateTimeField()),
                    timedelta(hours=0)),
                'epoch') / 3600,
            FloatField()),
        hours_fact=F('hours_fact_0') - breaktime_fact,
        hours_plan=F('hours_plan_0') - breaktime_plan
    )


def wd_stat_count_total(worker_days, shop):
    return wd_stat_count(worker_days, shop).aggregate(
        hours_count_fact=Sum('hours_fact'),
        hours_count_plan=Sum('hours_plan'),
        lateness_count=Sum('is_late'),
        ticks_coming_count=Count('coming'),
        ticks_leaving_count=Count('leaving')
    )


class CleanWdaysHelper:
    """
    Класс, предназначенный для того, чтобы корректировать рабочие дни
    (изначально делался для того, чтобы пофиксить последствия того, что Ортека шлет трудоустройства задним числом)

    Проходит по всем дням, которые находятся с учетом filter_kwargs и exclude_kwargs
    Алгоритм для каждого дня:
    1. Если нету активного трудоустройства:
    1.1 Если тип дня один из [WorkerDay.TYPE_MATERNITY, WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK], то КОНЕЦ.
    1.2 В остальных случаях очищаем employment_id, КОНЕЦ.
    2. Если есть активное трудоустройство:
    2.1 Если employment в дне и в активном трудоустройстве не совпадают:
    2.1.1 Если clean_plan_empl=True и если в дне магазин не равен магазину из активного трудоустройства на этот день и is_vacancy=False,
        то очищаем employment, КОНЕЦ.
    2.1.2 В остальных случаях делаем employment в дне равным активному трудоустройству.
    #2.2 Если тип дня рабочий день (type == 'W'), то корректируем is_vacancy:
        если магазины в дне и в активном трудоустройстве отличаются, то ставим is_vacancy=True,
        если не отличаются, то ставим False
    #2.3 Если тип не в TYPES_WITH_TM_RANGE, то корректируем удаляем shop_id и проставляем is_vacancy=False
    КОНЕЦ.

    КОНЕЦ -- завершения алгоритма и переход к следующему дню сотрудника.
    """
    def __init__(
            self,
            filter_kwargs: dict = None,
            exclude_kwargs: dict = None,
            only_logging=True,
            clean_plan_empl=False,
            logger=logging.getLogger('clean_wdays'),
    ):
        self.filter_kwargs = filter_kwargs
        self.exclude_kwargs = exclude_kwargs
        self.only_logging = only_logging
        self.clean_plan_empl = clean_plan_empl

        self.logger = logger

    def _log_wd(self, wd, log_title, log_level='debug', extra=None):
        getattr(self.logger, log_level)(
            f'clean_wdays {log_title}: '
            'id=%s, dt=%s, type=%s, is_fact=%s, is_approved=%s, worker=%s, shop_id=%s, employment_id=%s, extra=%s',
            wd.id, wd.dt, wd.type, wd.is_fact, wd.is_approved, wd.worker.username, wd.shop_id, wd.employment_id, extra
        )

    def run(self):
        self.logger.info(
            'clean_wdays started, filter_kwargs: %s, exclude_kwargs: %s, only_logging: %s',
            self.filter_kwargs, self.exclude_kwargs, self.only_logging
        )

        wdays_qs = WorkerDay.objects_with_excluded.exclude(
            worker__isnull=True,
        ).exclude(
            type=WorkerDay.TYPE_EMPTY,
        ).order_by('dt', 'worker', 'shop')
        if self.filter_kwargs:
            wdays_qs = wdays_qs.filter(**self.filter_kwargs)
        if self.exclude_kwargs:
            wdays_qs = wdays_qs.exclude(**self.exclude_kwargs)

        not_found = 0
        changed = 0
        skipped = 0
        empl_cleaned = 0

        for worker_day in wdays_qs:
            with transaction.atomic() if not self.only_logging else dummy_context_mgr():
                wd_qs = WorkerDay.objects_with_excluded.filter(id=worker_day.id)
                if not self.only_logging:
                    wd_qs = wd_qs.select_for_update()
                wd = wd_qs.first()
                if wd is None:
                    self._log_wd(worker_day, 'not found')
                    not_found += 1
                    continue

                changes = {}

                worker_active_empl = Employment.objects.get_active_empl_for_user(
                    network_id=wd.worker.network_id, user_id=wd.worker_id, dt=wd.dt,
                    priority_shop_id=wd.shop_id, priority_employment_id=wd.employment_id,
                ).first()

                if not worker_active_empl:
                    if wd.type in [WorkerDay.TYPE_MATERNITY, WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK]:
                        continue

                    self._log_wd(wd, 'no active empl empl_cleaned')
                    empl_cleaned += 1
                    if not self.only_logging:
                        wd.employment_id = None
                        wd.save(update_fields=('employment_id',))

                    continue

                if wd.employment_id != worker_active_empl.id:
                    if self.clean_plan_empl and wd.is_fact is False and wd.shop_id \
                            and wd.shop_id != worker_active_empl.shop_id and wd.is_vacancy is False:
                        self._log_wd(wd, 'plan empl_cleaned')
                        empl_cleaned += 1
                        if not self.only_logging:
                            wd.employment_id = None
                            wd.save(update_fields=('employment_id',))
                        continue

                    changes.update({'employment_id': {
                        'from': wd.employment_id,
                        'to': worker_active_empl.id,
                    }})
                    wd.employment_id = worker_active_empl.id

                # if wd.type == WorkerDay.TYPE_WORKDAY:
                #     if wd.is_vacancy != (not worker_active_empl.is_equal_shops):
                #         changes.update({'is_vacancy': {
                #             'from': wd.is_vacancy,
                #             'to': not worker_active_empl.is_equal_shops,
                #         }})
                #         wd.is_vacancy = not worker_active_empl.is_equal_shops
                #
                # if wd.type not in WorkerDay.TYPES_WITH_TM_RANGE:
                #     if wd.shop_id is not None:
                #         changes.update({'shop_id': {
                #             'from': wd.shop_id,
                #             'to': None,
                #         }})
                #         wd.shop_id = None
                #     if wd.is_vacancy is True:
                #         changes.update({'is_vacancy': {
                #             'from': wd.is_vacancy,
                #             'to': False,
                #         }})
                #         wd.is_vacancy = False

                if changes:
                    self._log_wd(wd, 'changed', extra=changes)
                    changed += 1
                    if not self.only_logging:
                        wd.save()
                else:
                    self._log_wd(wd, 'skipped', extra=changes)
                    skipped += 1

        self.logger.info(
            'clean_wdays finished, results: not_found=%s, changed=%s, skipped=%s, empl_cleaned=%s',
            not_found, changed, skipped, empl_cleaned,
        )
        return {
            'not_found': not_found,
            'changed': changed,
            'skipped': skipped,
            'empl_cleaned': empl_cleaned,
        }
