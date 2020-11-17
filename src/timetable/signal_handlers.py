from src.timetable.models import (
    WorkerDay,
    WorkerDayPermission,
)


def create_worker_day_permissions(sender, **kwargs):
    existing_wd_perms = set(WorkerDayPermission.objects.values_list('wd_type', 'graph_type', 'action'))

    wd_permissions_to_create = []
    for wd_type in WorkerDay.TYPES_USED:
        for graph_type, _ in WorkerDayPermission.GRAPH_TYPES:
            for action, _ in WorkerDayPermission.ACTIONS:
                if (wd_type, graph_type, action) not in existing_wd_perms:
                    wd_permissions_to_create.append(
                        WorkerDayPermission(
                            wd_type=wd_type,
                            graph_type=graph_type,
                            action=action,
                        )
                    )

    if wd_permissions_to_create:
        WorkerDayPermission.objects.bulk_create(wd_permissions_to_create)

    WorkerDayPermission.objects.exclude(id__in=WorkerDayPermission.objects.filter(
        wd_type__in=WorkerDay.TYPES_USED,
        graph_type__in=[gt[0] for gt in WorkerDayPermission.GRAPH_TYPES],
        action__in=[a[0] for a in WorkerDayPermission.ACTIONS],
    )).delete()
