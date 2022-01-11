from django.db.models import Q
from src.timetable.models import EmploymentWorkType, WorkTypeName, WorkType, WorkerDayCashboxDetails
from src.base.models import Shop, WorkerPosition, Employment

def fix_work_types(work_type_name_ids_to_delete=[], work_type_name_codes_to_delete=[]):
    exclude_work_type_names = WorkTypeName.objects.filter(
        Q(id__in=work_type_name_ids_to_delete) |
        Q(code__in=work_type_name_codes_to_delete),
    )

    # создаем во всех магазинах типы работ
    for shop in Shop.objects.all():
        for work_type_name in WorkTypeName.objects.exclude(id__in=exclude_work_type_names.values_list('id', flat=True)):
            WorkType.objects.get_or_create(
                shop=shop,
                work_type_name=work_type_name,
            )

    # проставляем должностям типы работ по умолчанию
    for position in WorkerPosition.objects.all():
        position.save(force_set_defaults=True)
    
    # проставляем трудоустройствам типы работ по умолчанию
    for e in Employment.objects_with_excluded.all():
        e.save(force_create_work_types=True)

    # проставляем в рабочих днях "правильные" типы работ
    employment_work_types = {e.employment_id: e.work_type_id for e in EmploymentWorkType.objects.all()}
    details = list(WorkerDayCashboxDetails.objects.select_related('worker_day').all())

    for d in details: 
        work_type_id = employment_work_types.get(d.worker_day.employment_id)
        if work_type_id:
            d.work_type_id = work_type_id

    WorkerDayCashboxDetails.objects.bulk_update(details, fields=['work_type_id'], batch_size=1000)   

    # "удаляем" типы работ
    WorkType.objects.qos_delete(work_type_name__in=exclude_work_type_names)                                                                                          
