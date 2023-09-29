from rest_framework import serializers
from src.interfaces.api.serializers.base import BaseModelSerializer

from src.apps.timetable.models import WorkerDayType


class WorkerDayTypeSerializer(BaseModelSerializer):
    allowed_additional_types = serializers.SerializerMethodField()

    def get_allowed_additional_types(self, obj):
        return [t.code for t in obj.allowed_additional_types_list]

    class Meta:
        model = WorkerDayType
        fields = (
            'code',
            'name',
            'short_name',
            'html_color',
            'use_in_plan',
            'use_in_fact',
            'excel_load_code',
            'is_dayoff',
            'is_work_hours',
            'is_reduce_norm',
            'is_system',
            'show_stat_in_days',
            'show_stat_in_hours',
            'ordering',
            'is_active',
            'get_work_hours_method',
            'has_details',
            'allowed_additional_types',
        )
