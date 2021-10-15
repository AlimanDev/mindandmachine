from import_export import resources
from import_export.fields import Field

from src.timetable.models import GroupWorkerDayPermission, WorkerDayPermission


class GroupWorkerDayPermissionResource(resources.ModelResource):
    group = Field(
        attribute='group_id',
    )
    worker_day_permission = Field(
        attribute='worker_day_permission_id',
    )

    class Meta:
        model = GroupWorkerDayPermission
        skip_unchanged = True
        report_skipped = True
        import_id_fields = (
            'group',
            'worker_day_permission',
        )
        fields = (
            'worker_day_permission__action',
            'worker_day_permission__graph_type',
            'worker_day_permission__wd_type__name',
            'limit_days_in_past',
            'limit_days_in_future',
        )

    export_headers_mapping = {
        'worker_day_permission__action': 'Действие',
        'worker_day_permission__graph_type': 'Тип графика',
        'worker_day_permission__wd_type__name': 'Тип дня',
        'limit_days_in_past': 'Ограничение на дни в прошлом',
        'limit_days_in_future': 'Ограничение на дни в будущем',
    }

    def get_export_headers(self):
        headers = [
            self.export_headers_mapping.get(field.column_name) for field in self.get_export_fields()]
        return headers

    def dehydrate_worker_day_permission__action(self, obj):
        if obj.id:
            return obj.worker_day_permission.get_action_display()

    def dehydrate_worker_day_permission__graph_type(self, obj):
        if obj.id:
            return obj.worker_day_permission.get_graph_type_display()

    def get_export_fields(self):
        return [self.fields[f] for f in self.Meta.fields]

    def before_import(self, dataset, using_transactions, dry_run, **kwargs):
        data = dataset.dict
        new_data = []
        wdp_dict = {f'{wdp.get_action_display()}_{wdp.get_graph_type_display()}_{wdp.wd_type.name}': wdp.id for wdp in
                    WorkerDayPermission.objects.select_related('wd_type')}
        for row in data:
            for gid in kwargs.get('groups', []):
                row_copy = row.copy()
                action = row_copy.pop('Действие')
                graph_type = row_copy.pop('Тип графика')
                wd_type_name = row_copy.pop('Тип дня')
                wdp_id = wdp_dict.get(f'{action}_{graph_type}_{wd_type_name}')
                if not wdp_id:
                    continue

                row_copy['worker_day_permission'] = wdp_id
                row_copy['group'] = gid
                row_copy['limit_days_in_past'] = row_copy.pop('Ограничение на дни в прошлом')
                row_copy['limit_days_in_future'] = row_copy.pop('Ограничение на дни в будущем')
                new_data.append(row_copy)
        dataset.dict = new_data
