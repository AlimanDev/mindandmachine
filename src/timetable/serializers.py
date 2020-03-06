from rest_framework import serializers
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkerDayApprove


class WorkerDayApproveSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(required=True)
    created_by = serializers.PrimaryKeyRelatedField(read_only=True, default=serializers.CurrentUserDefault())
    class Meta:
        model = WorkerDayApprove
        fields = ['id', 'shop_id', 'dt_approved', 'created_by']


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    work_type_id = serializers.IntegerField(required=False)
    class Meta:
        model = WorkerDayCashboxDetails
        fields = ['id', 'work_type_id', 'dttm_from', 'dttm_to', 'status']

class WorkerDaySerializer(serializers.ModelSerializer):
    worker_day_details = WorkerDayCashboxDetailsSerializer(many=True, required=False)
    worker_id = serializers.IntegerField(required=False)
    employment_id = serializers.IntegerField(required=False)
    shop_id = serializers.IntegerField(required=False)

    class Meta:
        model = WorkerDay
        fields = ['id', 'worker_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'worker_day_approve_id', 'worker_day_details']

    def create(self, validated_data):
        details = validated_data.pop('worker_day_details', None)
        worker_day = WorkerDay.objects.create(**validated_data)
        if details:
            for wd_detail in details:
                WorkerDayCashboxDetails.objects.create(worker_day=worker_day, **wd_detail)
        return worker_day

    
