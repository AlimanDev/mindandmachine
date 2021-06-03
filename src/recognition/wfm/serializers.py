from datetime import timedelta, datetime

from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, Shop, User
from src.base.serializers import NetworkSerializer


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = WorkerDayCashboxDetails
        fields = ['id', 'work_type_id', 'work_part', 'name']

    def get_name(self, obj) -> str:
        if obj.work_type and obj.work_type.work_type_name:
            return obj.work_type.work_type_name.name

class ShopSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shop
        fields = ['id', 'name']


class WorkerDayListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    dttm_work_start = serializers.DateTimeField()
    dttm_work_end = serializers.DateTimeField()


class WfmEmployeeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    tabel_code = serializers.CharField()
    worker_days = WorkerDayListSerializer(many=True)
    shop = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()

    def get_position(self, obj):
        employment = obj.employments.all()[0] if obj.employments.all() else None
        return employment.position.name if employment and employment.position else ''

    def get_shop(self, obj):
        employment = obj.employments.all()[0] if obj.employments.all() else None
        return ShopSerializer(employment.shop).data if employment else {}


class WfmWorkerDaySerializer(serializers.ModelSerializer):
    user_id = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()
    employees = WfmEmployeeSerializer(many=True)
    network = NetworkSerializer()

    class Meta:
        model = User
        fields = ['user_id', 'employees', 'first_name', 'last_name', 'avatar', 'network']

    def get_user_id(self, obj) -> int:
        return obj.id

    def get_avatar(self, obj) -> str:
        if obj.avatar:
            return obj.avatar.url
        return None



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
