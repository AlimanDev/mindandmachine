import calendar
from django.utils.translation import gettext as _
from django.conf import settings
from rest_framework import serializers

from ..models import TimesheetItem


class TimesheetItemSerializer(serializers.ModelSerializer):
    employee__tabel_code = serializers.CharField(read_only=True)
    shop_code = serializers.CharField(read_only=True)
    position_code = serializers.CharField(read_only=True)
    work_type_name_code = serializers.CharField(read_only=True)

    class Meta:
        model = TimesheetItem
        fields = (
            'id',
            'employee_id',
            'employee__tabel_code',
            'dt',
            'shop_id',
            'shop_code',
            'position_id',
            'position_code',
            'work_type_name_id',
            'work_type_name_code',
            'day_type',
            'dttm_work_start',
            'dttm_work_end',
            'day_hours',
            'night_hours',
            'source',
        )


class TimesheetSummarySerializer(serializers.ModelSerializer):
    employee__tabel_code = serializers.CharField(read_only=True)
    fact_timesheet_type = serializers.CharField(read_only=True)
    fact_timesheet_total_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)
    fact_timesheet_day_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)
    fact_timesheet_night_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)
    main_timesheet_type = serializers.CharField(read_only=True)
    main_timesheet_total_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)
    main_timesheet_day_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)
    main_timesheet_night_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)
    additional_timesheet_hours = serializers.DecimalField(read_only=True, max_digits=4, decimal_places=2)

    class Meta:
        model = TimesheetItem
        fields = (
            'employee_id',
            'employee__tabel_code',
            'dt',
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


class TimesheetRecalcSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField(format=settings.QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=settings.QOS_DATE_FORMAT)
    employee_id__in = serializers.ListField(child=serializers.IntegerField(), required=False)

    def validate(self, attrs):
        if not attrs.get('dt_from').day == 1:
            raise serializers.ValidationError({'detail': _('The start date must be the first day of the month.')})

        if not attrs.get('dt_to').day == calendar.monthrange(attrs.get('dt_to').year, attrs.get('dt_to').month)[1]:
            raise serializers.ValidationError({'detail': _('The end date must be the last day of the month.')})

        if not attrs.get('dt_from').month == attrs.get('dt_to').month:
            raise serializers.ValidationError({'detail': _('Recalculation can only be run for 1 month.')})

        return attrs
