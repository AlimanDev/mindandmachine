from src.base.serializers import BaseModelSerializer

from src.timetable.models import AttendanceRecords


class AttendanceRecordsSerializer(BaseModelSerializer):
    class Meta:
        model = AttendanceRecords
        fields = ['id', 'dt', 'dttm', 'type', 'user_id', 'employee_id', 'verified', 'terminal', 'shop_id']
