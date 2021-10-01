from datetime import timedelta

from django.db.models import OuterRef, F, Exists, Count

from src.base.models import Employment


def clean_empl_duplicates():
    empl_duplicates = list(Employment.objects.values(
        'employee_id',
        'dt_hired',
        'dt_fired',
        'shop_id',
        'position_id',
    ).annotate(
        count=Count('employee_id'),
    ).filter(
        count__gt=1,
    ))
    for empl_duplicate in empl_duplicates:
        empl_duplicate.pop('count')
        for employment in Employment.objects.filter(**empl_duplicate).order_by('-dttm_added')[1:]:
            employment.delete()


def fix_employment_dt_fired():
    Employment.objects.annotate(
        dt_hired_as_dt_fired_exists=Exists(
            Employment.objects.filter(
                dt_hired=OuterRef('dt_fired'),
                employee_id=OuterRef('employee_id'),
            )
        )
    ).filter(
        dt_hired_as_dt_fired_exists=True,
    ).update(
        dt_fired=F('dt_fired') - timedelta(days=1),
    )
