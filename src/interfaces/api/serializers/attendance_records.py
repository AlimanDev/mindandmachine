from src.interfaces.api.serializers.base import BaseModelSerializer

from src.apps.timetable.models import AttendanceRecords


class AttendanceRecordsSerializer(BaseModelSerializer):
    class Meta:
        model = AttendanceRecords
        fields = ['id', 'dt', 'dttm', 'type', 'user_id', 'employee_id', 'verified', 'terminal', 'shop_id']
