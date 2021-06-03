from rest_framework import serializers

from ..models import Timesheet


class TimesheetSerializer(serializers.ModelSerializer):
    employee__tabel_code = serializers.CharField(read_only=True)
    shop__code = serializers.CharField(read_only=True)

    class Meta:
        model = Timesheet
        fields = (
            'id',
            'employee_id',
            'employee__tabel_code',
            'dt',
            'shop_id',
            'shop__code',
            'fact_timesheet_type',
            'fact_timesheet_total_hours',
            'fact_timesheet_day_hours',
            'fact_timesheet_night_hours',
            'main_timesheet_type',
            'main_timesheet_total_hours',
            'main_timesheet_day_hours',
            'main_timesheet_night_hours',
            'additional_timesheet_hours',
        )
