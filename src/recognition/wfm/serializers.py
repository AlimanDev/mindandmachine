from datetime import timedelta, datetime

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, Shop, User


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = WorkerDayCashboxDetails
        fields = ['id', 'work_type_id', 'work_part', 'name']

    def get_name(self, obj) -> str:
        if obj.work_type and obj.work_type.work_type_name:
            return obj.work_type.work_type_name.name


class WorkerDaySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    dttm_work_start = serializers.DateTimeField()
    dttm_work_end = serializers.DateTimeField()
    position = serializers.SerializerMethodField()

    def get_position(self, obj):
        return obj.employment.position.name if obj.employment and obj.employment.position else ''


class EmployeeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    tabel_code = serializers.CharField()
    worker_days = WorkerDaySerializer(many=True)


class WorkerDaySerializer(serializers.ModelSerializer):
    user_id = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    employees = EmployeeSerializer(many=True)

    class Meta:
        model = User
        fields = ['user_id', 'employees', 'first_name', 'last_name', 'avatar']

    def get_user_id(self, obj) -> int:
        return obj.id

    def get_avatar(self, obj) -> str:
        if obj.avatar:
            return obj.avatar.url
        return None


class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ['id', 'name']


class WorkShiftSerializer(serializers.ModelSerializer):
    dt = serializers.DateField()
    worker = serializers.CharField(source='employee.user.username')
    shop = serializers.CharField(source='shop.code')

    # переопределение нужно, чтобы возвращать время в реальном utc
    dttm_work_start = serializers.SerializerMethodField()
    dttm_work_end = serializers.SerializerMethodField()

    def get_dttm_work_start(self, wd) -> datetime:
        return (wd.dttm_work_start - timedelta(
            hours=wd.shop.get_tz_offset())).isoformat() if wd.dttm_work_start else None

    def get_dttm_work_end(self, wd) -> datetime:
        return (wd.dttm_work_end - timedelta(hours=wd.shop.get_tz_offset())).isoformat() if wd.dttm_work_end else None

    class Meta:
        model = WorkerDay
        fields = (
            'dt',
            'dttm_work_start',
            'dttm_work_end',
            'worker',
            'shop',
        )
