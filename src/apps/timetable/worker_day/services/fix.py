from django.db.models import Q, OuterRef, Subquery, F
from django.db import transaction

from src.common.service import Service
from src.apps.base.models import Employment
from src.apps.timetable.models import WorkerDay, WorkerDayCashboxDetails, EmploymentWorkType


class FixWdaysService(Service):
    """
    Fix WorkerDays by reattaching correct Employments and WorkerDayTypes.
    For example, when Employment changes and WorkerDays are left with old data.
    """
    def __init__(self, **kwargs):
        self.filter_kwargs = kwargs

    def run(self) -> dict[str, int]:
        return {
            'days_employments_updated': self.fix_wd_employments(**self.filter_kwargs),
            'days_work_type_updated': self.fix_work_types(**self.filter_kwargs)
        }


    @staticmethod
    def fix_wd_employments(**filters) -> int:
        return WorkerDay.objects_with_excluded.filter(
            Q(employee__isnull=False),
            Q(employment__isnull=True) |
            Q(employment__dttm_deleted__isnull=False) |
            Q(Q(dt__lt=F('employment__dt_hired')) | Q(dt__gt=F('employment__dt_fired'))),
            **filters,
        ).exclude(
            type_id=WorkerDay.TYPE_EMPTY,
        ).update(
            employment_id=Subquery(Employment.objects.get_active_empl_by_priority(
                dt=OuterRef('dt'),
                employee_id=OuterRef('employee_id'),
                norm_work_hours__gt=0,
            ).values('id')[:1]),
        )

    @staticmethod
    @transaction.atomic
    def fix_work_types(**filters):
        """
        Changes work_types to 1 from employment.work_types (highest priority).
        Won't work if there are no work_types (WorkerDayCashboxDetails) attached to the WorkerDay.
        """
        wdays = WorkerDay.objects.filter(
                employment__work_types__isnull=False,
                is_vacancy=False,                                   # Vacancies are not included - usually other work_type in employment
                **filters
        )
        details = WorkerDayCashboxDetails.objects.filter(
            worker_day__in=wdays
        ).annotate(
            new_work_type_id=EmploymentWorkType.objects.filter(
                employment=OuterRef('worker_day__employment'),
                is_active=True
            ).order_by(
                '-priority', '-work_type__priority', '-id'          # TODO: Why there are 2 `priority` in both tables?
            ).values_list('work_type')[:1]
        ).select_for_update()                                       # Lock rows for editing
        for detail in details:                                      # Doesn't work with update() - OuterRef across relationship is not supported
            detail.work_type_id = detail.new_work_type_id
            detail.save()
        return len(details)                                         # Number of all `save()` calls, not necessarily changed.
