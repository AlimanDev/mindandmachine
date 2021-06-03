from rest_framework import serializers

from ..models import Timesheet


class TimesheetSerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField()
    shop_id = serializers.IntegerField()
    employee__tabel_code = serializers.CharField()

    class Meta:
        model = Timesheet
        fields = (
            'id',
            'employee_id',
            'employee__tabel_code',
            'dt',
            'shop_id',
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
