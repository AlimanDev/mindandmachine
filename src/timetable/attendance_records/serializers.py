from rest_framework import serializers

from src.timetable.models import AttendanceRecords


class AttendanceRecordsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AttendanceRecords
        fields = ['id', 'dt', 'dttm', 'type', 'user_id', 'employee_id', 'verified', 'terminal', 'shop_id']
