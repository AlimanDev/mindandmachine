from import_export import resources
from import_export.fields import Field

from src.timetable.models import GroupWorkerDayPermission, WorkerDayPermission


class GroupWorkerDayPermissionResource(resources.ModelResource):
    group = Field(attribute='group_id')
    worker_day_permission = Field(attribute='worker_day_permission_id')

    class Meta:
        model = GroupWorkerDayPermission
        import_id_fields = (
            'group',
            'worker_day_permission',
            'limit_days_in_past',
            'limit_days_in_future',
        )
        fields = (
            'worker_day_permission__action',
            'worker_day_permission__graph_type',
            'worker_day_permission__wd_type__code',
            'limit_days_in_past',
            'limit_days_in_future',
        )

    def get_export_fields(self):
        return [self.fields[f] for f in self.Meta.fields]

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        data = dataset.dict
        new_data = []
        wdp_dict = {f'{wdp.action}_{wdp.graph_type}_{wdp.wd_type_id}': wdp.id for wdp in WorkerDayPermission.objects.all()}
        for row in data:
            for gid in kwargs.get('groups', []):
                row = row.copy()
                action = row.pop('worker_day_permission__action')
                graph_type = row.pop('worker_day_permission__graph_type')
                wd_type_id = row.pop('worker_day_permission__wd_type__code')
                wdp_id = wdp_dict.get(f'{action}_{graph_type}_{wd_type_id}')
                if not wdp_id:
                    continue

                row['worker_day_permission'] = wdp_id
                row['group'] = gid
                new_data.append(row)
        dataset.dict = new_data
