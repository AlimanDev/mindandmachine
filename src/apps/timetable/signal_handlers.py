import logging

from django.db.models.signals import post_save, pre_delete
from django.dispatch import receiver

from src.apps.timetable.models import (
    WorkerDayPermission,
    WorkerDayType, WorkerDay,
)


logger = logging.getLogger('attendance_records')


def create_worker_day_permissions(sender, **kwargs):
    existing_wd_perms = set(WorkerDayPermission.objects.values_list('wd_type_id', 'graph_type', 'action'))

    wd_permissions_to_create = []
    existing_wd_type_ids = list(WorkerDayType.objects.values_list('code', flat=True))
    for wd_type_id in existing_wd_type_ids:
        for graph_type, _ in WorkerDayPermission.GRAPH_TYPES:
            for action, _ in WorkerDayPermission.ACTIONS:
                if (wd_type_id, graph_type, action) not in existing_wd_perms:
                    wd_permissions_to_create.append(
                        WorkerDayPermission(
                            wd_type_id=wd_type_id,
                            graph_type=graph_type,
                            action=action,
                        )
                    )

    if wd_permissions_to_create:
        WorkerDayPermission.objects.bulk_create(wd_permissions_to_create)

    WorkerDayPermission.objects.exclude(id__in=WorkerDayPermission.objects.filter(
        wd_type_id__in=existing_wd_type_ids,
        graph_type__in=[gt[0] for gt in WorkerDayPermission.GRAPH_TYPES],
        action__in=[a[0] for a in WorkerDayPermission.ACTIONS],
    )).delete()


@receiver(post_save, sender=WorkerDayType)
def create_wd_perm(sender, instance, created, **kwargs):
    if created:
        WorkerDayPermission.objects.bulk_create([
            WorkerDayPermission(
                wd_type=instance,
                graph_type=graph_type,
                action=action,
            )
            for graph_type, _ in WorkerDayPermission.GRAPH_TYPES
            for action, _ in WorkerDayPermission.ACTIONS
        ])


@receiver(pre_delete, sender=WorkerDay)
def log_worker_day_deletion(sender, instance, **kwargs):
    """Логаем удаление подтвержденных фактов"""
    if instance.is_fact and instance.is_approved:
        logger.info(
            f'Удаляем подтвержденный факт для {instance.employee.user.last_name} {instance.employee.user.first_name} '
            f'за {instance.dttm} время начала {instance.dttm_work_start} время конца {instance.dttm_work_end}')
