from rest_framework import serializers
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, EmploymentWorkType, WorkerConstraint

from rest_framework.exceptions import ValidationError
from  django.db import DatabaseError
from src.base.models import Employment, User
from src.util.models_converter import Converter
from src.conf.djconfig import QOS_DATE_FORMAT
from src.base.exceptions import MessageError


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
        is_fact = attrs.get('is_fact')
        if is_fact:
            attrs['type'] = WorkerDay.TYPE_WORKDAY

        type = attrs['type']


        if not WorkerDay.is_type_with_tm_range(type):
            attrs['dttm_work_start'] = None
            attrs['dttm_work_end'] = None
        elif not ( attrs.get('dttm_work_start') and attrs.get('dttm_work_end')):
            raise ValidationError({"error": f"dttm_work_start, dttm_work_end are required for type {type}"})
        elif attrs['dttm_work_start'] > attrs['dttm_work_end'] or attrs['dt'] != attrs['dttm_work_start'].date() or attrs['dt'] != attrs['dttm_work_end'].date():
            raise ValidationError({"error": f"dttm_work_start must be less then dttm_work_end and has the same date as dt"})




        if not type == WorkerDay.TYPE_WORKDAY or is_fact:
            attrs.pop('worker_day_details', None)
        elif not ( attrs.get('worker_day_details')):
            raise ValidationError({"error": f" worker_day_details is required for type {type}"})
        return attrs

    def create(self, validated_data):
        self.check_other_worker_days(None, validated_data)

        is_fact = validated_data.get('is_fact')
        parent_worker_day_id = validated_data.get('parent_worker_day_id', None)

        # Если создаем факт то делаем его потомком плана. Если создаем план - делаем родителем факта
        worker_day_to_bind = None
        if not parent_worker_day_id:
            worker_days = WorkerDay.objects.filter(
                worker_id=validated_data.get('worker_id'),
                is_fact=not is_fact,
                dt=validated_data.get('dt'),
                shop_id=validated_data.get('shop_id'),
            )
            wd = {True: None, False: None}

            for w in worker_days:
                wd[w.is_approved] = w

            worker_day_to_bind = wd[True] if wd[True] else wd[False]
            if is_fact and worker_day_to_bind:
                validated_data['parent_worker_day_id'] = worker_day_to_bind.id

        details = validated_data.pop('worker_day_details', None)

        worker_day = WorkerDay.objects.create(**validated_data)

        if not is_fact:
            if worker_day_to_bind:
                worker_day_to_bind.parent_worker_day = worker_day
                worker_day_to_bind.save()
            if details:
                for wd_detail in details:
                    WorkerDayCashboxDetails.objects.create(worker_day=worker_day, **wd_detail)

        return worker_day

    def update(self, instance, validated_data):
        self.check_other_worker_days(instance, validated_data)

        details = validated_data.pop('worker_day_details', [])

        if not instance.is_fact:
            WorkerDayCashboxDetails.objects.filter(worker_day=instance).delete()
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

class WorkerDayWithParentSerializer(WorkerDaySerializer):
    parent_worker_day_id = serializers.IntegerField()


class EmploymentWorkTypeSerializer(serializers.ModelSerializer):
    employment_id = serializers.IntegerField(required=False)
    work_type_id = serializers.IntegerField(required=False)

    class Meta:
        model = EmploymentWorkType
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


class ListChangeSrializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    workers = serializers.JSONField()
    type = serializers.CharField()
    tm_work_start = serializers.TimeField(required=False)
    tm_work_end = serializers.TimeField(required=False)
    work_type_id = serializers.IntegerField(required=False)
    comment = serializers.CharField(max_length=128, required=False)


    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if WorkerDay.is_type_with_tm_range(self.validated_data['type']):
            if self.validated_data.get('tm_work_start') is None:
                raise MessageError(code="tm_work_start_req", lang=self.context['request'].user.lang)
            if self.validated_data.get('tm_work_end') is None:
                raise MessageError(code="tm_work_end_req", lang=self.context['request'].user.lang)
            workers = self.validated_data.get('workers')
            for key, value in workers:
                try:
                    workers[key] = list(map(lambda x: Converter.parse_date(x), value))
                except:
                    raise MessageError(code="invalid_dt_change_list", lang=self.context['request'].user.lang)


class DuplicateSrializer(serializers.Serializer):
    from_worker_id = serializers.IntegerField()
    to_worker_id = serializers.IntegerField()
    from_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    to_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    is_approved = serializers.BooleanField(default=False)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if not User.objects.filter(id=self.validated_data['from_worker_id']).exists():
            raise MessageError(code="duplicate_wd_main_user", lang=self.context['request'].user.lang)
        if not User.objects.filter(id=self.validated_data['to_worker_id']).exists():
            raise MessageError(code="duplicate_wd_trainer_user", lang=self.context['request'].user.lang)
        if self.validated_data['from_dt'] > self.validated_data['to_dt']:
            raise MessageError(code="dt_from_gt_dt_to", lang=self.context['request'].user.lang)


class DeleteTimetableSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT, required=False)
    users = serializers.ListField(child=serializers.IntegerField(), required=False)
    types = serializers.ListField(child=serializers.CharField(), required=False)
    delete_all = serializers.BooleanField(default=False)
    except_created_by = serializers.BooleanField(default=True)
    
    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        dt_from = self.validated_data.get('dt_from')
        dt_to = self.validated_data.get('dt_to')
        
        if not self.validated_data.get('delete all') and not dt_to:
            raise MessageError(code="dt_to_required", lang=self.context['request'].user.lang)

        if dt_to and dt_from > dt_to:
            raise MessageError(code="dt_from_gt_dt_to", lang=self.context['request'].user.lang)


class ExchangeSerializer(serializers.Serializer):
    worker1_id = serializers.IntegerField()
    worker2_id = serializers.IntegerField()
    from_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    to_dt = serializers.DateField(format=QOS_DATE_FORMAT)
    is_approved = serializers.BooleanField(default=False)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if not User.objects.filter(id=self.validated_data['from_worker_id']).exists():
            raise MessageError(code="exchange_user", lang=self.context['request'].user.lang)
        if not User.objects.filter(id=self.validated_data['to_worker_id']).exists():
            raise MessageError(code="exchange_user", lang=self.context['request'].user.lang)
        if self.validated_data['from_dt'] > self.validated_data['to_dt']:
            raise MessageError(code="dt_from_gt_dt_to", lang=self.context['request'].user.lang)
