from rest_framework import serializers
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkerWorkType, WorkerConstraint

from rest_framework.exceptions import ValidationError
from  django.db import DatabaseError
from src.base.models import Employment


class WorkerDayApproveSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField(required=True)
    is_fact = serializers.BooleanField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()


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
    parent_worker_day_id = serializers.IntegerField(required=False, read_only=True)
    is_fact = serializers.BooleanField(required=False)
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    type = serializers.CharField(required=True)

    class Meta:
        model = WorkerDay
        fields = ['id', 'worker_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'is_approved', 'worker_day_details', 'is_fact', 'work_hours','parent_worker_day_id']
        read_only_fields =['is_approved', 'work_hours', 'parent_worker_day_id']
        create_only_fields = ['is_fact']
    def validate(self, attrs):
        type = attrs['type']

        if not WorkerDay.is_type_with_tm_range(type):
            attrs['dttm_work_start'] = None
            attrs['dttm_work_end'] = None
            attrs['worker_day_details'] = []
        elif not ( attrs['dttm_work_start'] and attrs['dttm_work_end'] and attrs['worker_day_details']):
            raise ValidationError({"error": f"dttm_work_start, dttm_work_end, and worker_day_details required for type {type}"})
        return attrs



    def create(self, validated_data):
        self.check_other_worker_days(None, validated_data)

        is_fact = validated_data.get('is_fact')
        parent_worker_day_id = validated_data.get('parent_worker_day_id', None)

        if is_fact and not parent_worker_day_id:
            worker_day = WorkerDay.objects.filter(
                worker_id=validated_data.get('worker_id'),
                is_fact=False,
                dt=validated_data.get('dt'),
                shop_id=validated_data.get('shop_id'),
            ).first()
            if not worker_day:
                raise ValidationError({"error": f"Нельзя занести фактическое время в отсутствие планового графика"})
            validated_data['parent_worker_day_id']=worker_day.id

        details = validated_data.pop('worker_day_details', None)

        worker_day = WorkerDay.objects.create(**validated_data)

        if not is_fact and details:
            for wd_detail in details:
                WorkerDayCashboxDetails.objects.create(worker_day=worker_day, **wd_detail)

        return worker_day

    def update(self, instance, validated_data):
        self.check_other_worker_days(instance, validated_data)

        details = validated_data.pop('worker_day_details', None)

        if not instance.is_fact:
            WorkerDayCashboxDetails.objects.filter(worker_day=instance).delete()
            if details:
                for wd_detail in details:
                    WorkerDayCashboxDetails.objects.create(worker_day=instance, **wd_detail)

        return super().update(instance, validated_data)

    def check_other_worker_days(self, worker_day, validated_data):
        """
        При сохранении рабочего дня проверяет, что нет пересечений с другими рабочими днями в тот же день
        """
        is_fact = worker_day.is_fact if worker_day else validated_data.get('is_fact')
        worker_days = WorkerDay.objects.filter(
            worker_id=validated_data.get('worker_id'),
            dt=validated_data.get('dt'),
            is_fact=is_fact,
        )

        if worker_day:
            worker_days = worker_days.exclude(id=worker_day.id)
            parent_worker_day_id = worker_day.parent_worker_day_id
        else:
            parent_worker_day_id = validated_data.get('parent_worker_day_id', None)

        if parent_worker_day_id:
            worker_days = worker_days.exclude(id=parent_worker_day_id)

        for wd in worker_days:
            # может быть смена в другое время в тот же день, других workerday быть не должно
            if wd.type == WorkerDay.TYPE_WORKDAY and validated_data.get('type') == WorkerDay.TYPE_WORKDAY:
                if wd.dttm_work_start <=validated_data.get('dttm_work_end') and \
                   wd.dttm_work_end >= validated_data.get('dttm_work_start'):
                    raise ValidationError({"error":f"Рабочий день пересекается с существующим рабочим днем. {wd.shop.name} {wd.dttm_work_start} {wd.dttm_work_end}"})
            else:
                raise ValidationError({"error": f"У сотрудника уже существует рабочий день: {wd} "})

    def to_internal_value(self, data):
        data = super(WorkerDaySerializer, self).to_internal_value(data)
        if self.instance:
            # update
            for field in self.Meta.create_only_fields:
                if field in data:
                    data.pop(field)
        else:
            # shop_id is required for create
            for field in self.Meta.create_only_fields:
                if field not in data:
                    raise serializers.ValidationError({field:"This field is required"})
        return data


class WorkerWorkTypeSerializer(serializers.ModelSerializer):
    employment_id = serializers.IntegerField(required=False)
    work_type_id = serializers.IntegerField(required=False)

    class Meta:
        model = WorkerWorkType
        fields = ['id', 'work_type_id', 'employment_id', 'period', 'bills_amount', 'priority', 'duration']


class WorkerConstraintListSerializer(serializers.ListSerializer):
    def create(self, validated_data):
        employment_id = validated_data[0].get('employment_id')
        employment = Employment.objects.get(id=employment_id)
        to_create = []
        ids = []

        constraints = WorkerConstraint.objects.filter(
            employment_id=employment_id,
        )
        constraint_mapping = {constraint.id: constraint for constraint in constraints}

        for item in validated_data:
            if item.get('id'):
                if not constraint_mapping.get(item['id']):
                    raise ValidationError({"error": f"object with id {item['id']} does not exist"})
                self.child.update(constraint_mapping[item['id']], item)
                ids.append(item['id'])
            else:
                constraint = WorkerConstraint(
                    **item,
                    worker_id=employment.user_id,
                    shop_id=employment.shop_id,
                )
                to_create.append(constraint)

        WorkerConstraint.objects.filter(
            employment_id=employment_id
        ).exclude(
            id__in=ids
        ).delete()

        WorkerConstraint.objects.bulk_create(to_create)
        return WorkerConstraint.objects.filter(employment_id=employment_id)


class WorkerConstraintSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)
    employment_id = serializers.IntegerField(required=True)

    class Meta:
        model = WorkerConstraint
        fields = ['id', 'employment_id', 'weekday', 'is_lite', 'tm']
        list_serializer_class = WorkerConstraintListSerializer
