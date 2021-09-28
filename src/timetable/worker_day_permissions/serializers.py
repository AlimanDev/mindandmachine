from rest_framework import serializers

from src.base.models import Shop
from src.timetable.models import WorkerDayPermission, GroupWorkerDayPermission, WorkerDay


class WorkerDayPermissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerDayPermission
        fields = (
            'action',
            'graph_type',
            'wd_type',
        )


class GroupWorkerDayPermissionSerializer(serializers.ModelSerializer):
    worker_day_permission = WorkerDayPermissionSerializer()

    class Meta:
        model = GroupWorkerDayPermission
        fields = (
            'worker_day_permission',
            'limit_days_in_past',
            'limit_days_in_future',
        )


class WorkerDayPermissionQueryStringSerializer(serializers.Serializer):
    action = serializers.ChoiceField(
        choices=WorkerDayPermission.ACTIONS, required=False, allow_null=False, allow_blank=False)
    graph_type = serializers.ChoiceField(
        choices=WorkerDayPermission.GRAPH_TYPES, required=False, allow_null=False, allow_blank=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['shop'] = serializers.PrimaryKeyRelatedField(
            required=True, allow_null=False,
            queryset=Shop.objects.filter(
                network=self.context['request'].user.network,
            ).select_related('network'),
        )


class WsPermissionDataSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerDay
        fields = (
            'dt',
            'type',
            'is_fact',
        )
        extra_kwargs = {
            "dt": {
                "error_messages": {
                    "required": "Поле дата не может быть пустым.",
                    "null": "Поле дата не может быть пустым.",
                },
            },
        }
