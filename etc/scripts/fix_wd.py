from django.db.models import Q, OuterRef
from django.db.models import Subquery, F

from src.base.models import Employment
from src.timetable.models import WorkerDay


def fix_wd_employments():
    WorkerDay.objects.filter(
        Q(employment__isnull=True) |
        Q(Q(dt__lt=F('employment__dt_hired')) | Q(dt__gt=F('employment__dt_fired'))),
    ).update(
        employment_id=Subquery(Employment.objects.get_active_empl_by_priority(
            dt=OuterRef('dt'),
            employee_id=OuterRef('employee_id'),
            norm_work_hours__gt=0,
        ).values('id')[:1]),
    )
