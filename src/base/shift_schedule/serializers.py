from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from src.base.fields import CurrentUserNetwork
from src.base.models import (
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleDayItem,
    ShiftScheduleInterval,
    Employee,
)


class ShiftScheduleDayItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShiftScheduleDayItem
        fields = (
            'id',
            'code',
            'hours_type',
            'hours_amount',
        )


class ShiftScheduleDaySerializer(serializers.ModelSerializer):
    items = ShiftScheduleDayItemSerializer(many=True)

    class Meta:
        model = ShiftScheduleDay
        fields = (
            'id',
            'code',
            'dt',
            'items',
        )


class ShiftScheduleSerializer(serializers.ModelSerializer):
    network_id = serializers.HiddenField(default=CurrentUserNetwork())
    days = ShiftScheduleDaySerializer(many=True)

    class Meta:
        model = ShiftSchedule
        fields = (
            'network_id',
            'id',
            'code',
            'name',
            'year',
            'days',
        )


class ShiftScheduleIntervalSerializer(serializers.ModelSerializer):
    employee__tabel_code = serializers.CharField(required=False, source='employee.tabel_code')
    shift_schedule__code = serializers.CharField(required=False, source='shift_schedule.code')

    default_error_messages = {
        "no_employee_with_tabel_code": _("There are {amount} models of employee with tabel_code: {tabel_code}."),
        "no_shift_schedule_with_code": _("There are {amount} models of shift_schedule with code: {code}."),
    }

    class Meta:
        model = ShiftScheduleInterval
        fields = (
            'id',
            'code',
            'employee_id',
            'employee__tabel_code',
            'shift_schedule_id',
            'shift_schedule__code',
            'dt_start',
            'dt_end',
        )

    def validate(self, attrs):
        # TODO: оптимизация получения связанных объектов ?
        employee = attrs.pop('employee', {})
        if not attrs.get('employee_id') and 'tabel_code' in employee:
            tabel_code = employee.pop('tabel_code', None)
            employees = list(Employee.objects.filter(
                tabel_code=tabel_code,
                user__network_id=self.context['request'].user.network_id,
            ).only('id'))
            if len(employees) == 1:
                attrs['employee_id'] = employees[0].id
            else:
                self.fail('no_employee_with_tabel_code', amount=len(employees), tabel_code=tabel_code)

        shift_schedule = attrs.pop('shift_schedule', {})
        if not attrs.get('shift_schedule_id') and 'code' in shift_schedule:
            code = shift_schedule.pop('code', None)
            shift_schedules = list(ShiftSchedule.objects.filter(
                code=code,
                network_id=self.context['request'].user.network_id,
            ).only('id'))
            if len(shift_schedules) == 1:
                attrs['shift_schedule_id'] = shift_schedules[0].id
            else:
                self.fail('no_shift_schedule_with_code', amount=len(shift_schedules), code=code)

        return attrs
