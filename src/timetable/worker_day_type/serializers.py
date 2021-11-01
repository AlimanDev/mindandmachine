from rest_framework import serializers

from src.timetable.models import WorkerDayType


class WorkerDayTypeSerializer(serializers.ModelSerializer):
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
        )
