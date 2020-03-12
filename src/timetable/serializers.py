from rest_framework import serializers
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkerDayApprove

from rest_framework.exceptions import ValidationError


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
    worker_id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    shop_id = serializers.IntegerField()

    class Meta:
        model = WorkerDay
        fields = ['id', 'worker_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'worker_day_approve_id', 'worker_day_details']
        read_only_fields =['worker_day_approve_id' ]

    def create(self, validated_data):
        worker_days = WorkerDay.objects.filter(
            worker_id=validated_data.get('worker_id'),
            dt=validated_data.get('dt'),
        )

        for wd in  worker_days:
            # может быть смена в другое время в тот же день, других workerday быть не должно
            if wd.type == WorkerDay.TYPE_WORKDAY and validated_data.get('type') == WorkerDay.TYPE_WORKDAY:
                if wd.dttm_work_start <=validated_data.get('dttm_work_end') and \
                   wd.dttm_work_end >= validated_data.get('dttm_work_start'):
                    raise ValidationError({"error":f"Рабочий день пересекается с существующим рабочим днем. {wd.shop.name} {wd.dttm_work_start} {wd.dttm_work_end}"})
            else:
                raise ValidationError({"error": f"У сотрудника уже существует рабочий день: {wd} "})

        details = validated_data.pop('worker_day_details', None)
        worker_day = WorkerDay.objects.create(**validated_data)

        if details:
            for wd_detail in details:
                WorkerDayCashboxDetails.objects.create(worker_day=worker_day, **wd_detail)

        return worker_day

    def update(self, instance, validated_data):
        worker_days = WorkerDay.objects.filter(
            worker_id=validated_data.get('worker_id'),
            dt=validated_data.get('dt'),
        ).exclude(
            id=instance.id
        )

        for wd in  worker_days:
            # может быть смена в другое время в тот же день, других workerday быть не должно
            if wd.type == WorkerDay.TYPE_WORKDAY and validated_data.get('type') == WorkerDay.TYPE_WORKDAY:
                if wd.dttm_work_start <=validated_data.get('dttm_work_end') and \
                   wd.dttm_work_end >= validated_data.get('dttm_work_start'):
                    raise ValidationError({"error":f"Рабочий день пересекается с существующим рабочим днем. {wd.shop.name} {wd.dttm_work_start} {wd.dttm_work_end}"})
            else:
                raise ValidationError({"error": f"У сотрудника уже существует рабочий день: {wd} "})

        details = validated_data.pop('worker_day_details', None)

        WorkerDayCashboxDetails.objects.filter(worker_day=instance).delete()
        if details:
            for wd_detail in details:
                # wd_detail_serializer=WorkerDayCashboxDetailsSerializer(data=wd_detail)
                # if wd_detail_serializer.is_valid():
                #     wd_detail_serializer.save()
                # else:
                #     raise ValidationError(wd_detail_serializer._errors)
                WorkerDayCashboxDetails.objects.create(worker_day=instance, **wd_detail)

        return super().update(instance, validated_data)
