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


class WorkerDaySerializer(serializers.ModelSerializer):
    user_id = serializers.SerializerMethodField()
    dttm_work_start = serializers.SerializerMethodField()
    dttm_work_end = serializers.SerializerMethodField()
    worker_day_id = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ['worker_day_id', 'user_id', 'first_name', 'last_name', 'dttm_work_start', 'dttm_work_end', 'avatar']

    def get_user_id(self, obj) -> int:
        return obj.id

    def get_avatar(self, obj) -> str:
        if obj.avatar:
            return obj.avatar.url
        return None

    def get_worker_day_id(self, obj) -> int:
        # method all() uses prefetch_related, but first() doesn't
        wd = WorkerDay.objects.filter(employee__user=obj)
        return wd[0].id if wd else None

    def get_dttm_work_start(self, obj) -> datetime:
        wd = WorkerDay.objects.filter(employee__user=obj)
        return wd[0].dttm_work_start if wd else None

    def get_dttm_work_end(self, obj) -> datetime:
        wd = list(WorkerDay.objects.filter(employee__user=obj))
        return wd[0].dttm_work_end if wd else None


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
