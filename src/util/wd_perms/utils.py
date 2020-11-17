from django.contrib import messages
from django.db import transaction

from src.timetable.models import WorkerDay, WorkerDayPermission, GroupWorkerDayPermission

ALL = '__all__'


class WdPermsPreset:
    wd_perms = None  # ((actions, graph_types, wd_types, days_limit_in_past, days_limit_in_future), ...)

    def delete_wd_perms(self, group):
        GroupWorkerDayPermission.objects.filter(group=group).delete()

    def create_wd_perms(self, group):
        wd_perms_dict = {(wdp.action, wdp.graph_type, wdp.wd_type): wdp for wdp in WorkerDayPermission.objects.all()}
        group_wd_perms = []
        for actions, graph_types, wd_types, limit_days_in_past, limit_days_in_future in self.wd_perms:
            if actions == ALL:
                actions = [i[0] for i in WorkerDayPermission.ACTIONS]
            if graph_types == ALL:
                graph_types = [i[0] for i in WorkerDayPermission.GRAPH_TYPES]
            if wd_types == ALL:
                wd_types = [i for i in WorkerDay.TYPES_USED]

            group_wd_perms.extend([GroupWorkerDayPermission(
                group=group,
                worker_day_permission=wd_perms_dict.get((action, graph_type, wd_type)),
                limit_days_in_past=limit_days_in_past,
                limit_days_in_future=limit_days_in_future,
            ) for action in actions for graph_type in graph_types for wd_type in wd_types if
                (action, graph_type, wd_type) in wd_perms_dict])

        GroupWorkerDayPermission.objects.bulk_create(group_wd_perms)

    def activate_preset(self, group):
        with transaction.atomic():
            self.delete_wd_perms(group)
            self.create_wd_perms(group)


class EmptyPreset(WdPermsPreset):
    wd_perms = ()


class AdminPreset(WdPermsPreset):
    wd_perms = (
        (ALL, [WorkerDayPermission.PLAN], ALL, None, None),
        (ALL, [WorkerDayPermission.FACT], WorkerDay.TYPES_WITH_TM_RANGE + (WorkerDay.TYPE_EMPTY,), None, None),
    )


class URSOrtekaPreset(WdPermsPreset):
    wd_perms = (
        (ALL, [WorkerDayPermission.PLAN], ALL, None, None),
        (ALL, [WorkerDayPermission.FACT], WorkerDay.TYPES_WITH_TM_RANGE + (WorkerDay.TYPE_EMPTY,), None, None),
    )


class DirectorOrtekaPreset(WdPermsPreset):
    wd_perms = (
        (
            [WorkerDayPermission.CREATE_OR_UPDATE, WorkerDayPermission.DELETE],
            [WorkerDayPermission.PLAN],
            ALL,
            7, 90
        ),
        (
            [WorkerDayPermission.APPROVE],
            [WorkerDayPermission.PLAN],
            [WorkerDay.TYPE_VACATION, WorkerDay.TYPE_SICK, WorkerDay.TYPE_SELF_VACATION],
            7, 90
        ),
        (
            [WorkerDayPermission.APPROVE],
            [WorkerDayPermission.FACT],
            [WorkerDay.TYPE_WORKDAY, WorkerDay.TYPE_QUALIFICATION],
            3, 0
        ),
        (
            [WorkerDayPermission.CREATE_OR_UPDATE, WorkerDayPermission.DELETE],
            [WorkerDayPermission.FACT],
            WorkerDay.TYPES_WITH_TM_RANGE + (WorkerDay.TYPE_EMPTY,),
            35, 0
        ),
    )


WD_PERMS_PRESETS = (
    ('Пустой', 'empty', EmptyPreset),  # Для удаления всех пермишнов
    ('Админ', 'admin', AdminPreset),
    ('УРС (Ортека)', 'urs_orteka', URSOrtekaPreset),
    ('Директор (Ортека)', 'dir_orteka', DirectorOrtekaPreset),
)


class WdPermsHelper:
    @classmethod
    def _get_set_preset_func(cls, preset, short_description):
        def set_preset_func(modeladmin, request, queryset):
            try:
                for role in queryset:
                    preset.activate_preset(role)
            except Exception as e:
                messages.error(request, f'Ошибка: {e}')
            else:
                messages.success(request, 'Пресет успешно установлен')

        set_preset_func.short_description = short_description
        return set_preset_func

    @classmethod
    def get_preset_actions(cls):
        actions = {}
        for preset_name, preset_alias, preset_cls in WD_PERMS_PRESETS:
            preset = preset_cls()
            action_alias = f'set_{preset_alias}_wd_perms_preset'
            short_description = f'Активировать пресет "{preset_name}"'
            actions[action_alias] = (
                cls._get_set_preset_func(preset, preset_name),
                action_alias,
                short_description,
            )

        return actions
