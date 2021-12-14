from datetime import timedelta

import pandas as pd
from django.db import transaction
from django.db.models import Q
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, ValidationError, NotFound

from src.base.exceptions import FieldError
from src.base.models import Employment, User, Shop, Employee, Network
from src.base.models import NetworkConnect
from src.base.serializers import NetworkListSerializer, UserShorSerializer, NetworkSerializer
from src.base.shop.serializers import ShopListSerializer, ShopSerializer
from src.conf.djconfig import QOS_DATE_FORMAT
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
    WorkerDayType,
    TimesheetItem,
)


class UnaccountedOvertimeMixin:
    def unaccounted_overtime_getter(self, obj):
        unaccounted_overtime = 0
        dttm_work_start = obj.dttm_work_start
        dttm_work_end = obj.dttm_work_end
        dttm_work_start_tabel = obj.dttm_work_start_tabel
        dttm_work_end_tabel = obj.dttm_work_end_tabel
        if all([dttm_work_start, dttm_work_end, dttm_work_start_tabel, dttm_work_end_tabel]):
            unaccounted_overtime = max(
                (dttm_work_end - dttm_work_end_tabel).total_seconds(), 
                0,
            ) + max(
                (dttm_work_start_tabel - dttm_work_start).total_seconds(), 
                0,
            )
        return unaccounted_overtime / 60


class RequestApproveSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    comment = serializers.CharField(allow_blank=True, required=False)
    is_fact = serializers.BooleanField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    employee_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
    )


class WorkerDayApproveSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField(required=True)
    is_fact = serializers.BooleanField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    wd_types = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=False,
        allow_null=False,
    )
    employee_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
    )


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    work_type_id = serializers.IntegerField(required=True)

    class Meta:
        model = WorkerDayCashboxDetails
        fields = ['id', 'work_type_id', 'work_part']


class WorkerDayCashboxDetailsListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    work_type_id = serializers.IntegerField()
    work_part = serializers.FloatField()


class WorkerDayListSerializer(serializers.Serializer, UnaccountedOvertimeMixin):
    id = serializers.IntegerField()
    worker_id = serializers.IntegerField(source='employee.user_id')
    employee_id = serializers.IntegerField()
    shop_id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    type = serializers.CharField(source='type_id')
    dt = serializers.DateField()
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    dttm_work_start_tabel = serializers.DateTimeField(default=None)
    dttm_work_end_tabel = serializers.DateTimeField(default=None)
    comment = serializers.CharField()
    is_approved = serializers.BooleanField()
    worker_day_details = WorkerDayCashboxDetailsListSerializer(many=True, source='worker_day_details_list')
    outsources = NetworkListSerializer(many=True, required=False, source='outsources_list')
    is_fact = serializers.BooleanField()
    work_hours = serializers.SerializerMethodField()
    shop_code = serializers.CharField(required=False)
    user_login = serializers.CharField(required=False)
    employment_tabel_code = serializers.CharField(required=False)
    created_by_id = serializers.IntegerField()
    last_edited_by = UserShorSerializer()
    dttm_modified = serializers.DateTimeField()
    is_blocked = serializers.BooleanField()
    unaccounted_overtime = serializers.SerializerMethodField()
    closest_plan_approved_id = serializers.IntegerField(read_only=True, required=False)
    cost_per_hour = serializers.DecimalField(None, None)
    total_cost = serializers.FloatField(read_only=True)

    def get_unaccounted_overtime(self, obj):
        return self.unaccounted_overtime_getter(obj)

    def get_work_hours(self, obj) -> float:
        if isinstance(obj.work_hours, timedelta):
            return obj.rounded_work_hours

        return obj.work_hours


class WorkerDaySerializer(serializers.ModelSerializer, UnaccountedOvertimeMixin):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
        'worker_day_exist': _("Worker day already exist."),
        'worker_day_intercept': _("Worker day intercepts with another: {shop_name}, {work_start}, {work_end}."),
        "no_user": _("There is {amount} models of user with username: {username}."),
        "wd_details_shop_mismatch": _("Shop in work type and in work day must match."),
        "user_mismatch": _("User in employment and in worker day must match."),
        "no_active_employments": _(
            "Can't create a working day in the schedule, since the user is not employed during this period"),
        "outsource_only_vacancy": _("Only vacancy can be outsource."),
        "outsources_not_specified": _("Outsources does not specified for outsource vacancy."),
        "no_such_shop_in_network": _("There is no such shop in your network."),
    }

    worker_day_details = WorkerDayCashboxDetailsSerializer(many=True, required=False)
    employee_id = serializers.IntegerField(required=False, allow_null=True)
    employment_id = serializers.IntegerField(required=False, allow_null=True)
    shop_id = serializers.IntegerField(required=False)
    parent_worker_day_id = serializers.IntegerField(required=False, read_only=True)
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    type = serializers.CharField(required=True, source='type_id')
    shop_code = serializers.CharField(required=False)
    user_login = serializers.CharField(required=False, read_only=True)
    employment_tabel_code = serializers.CharField(required=False, read_only=True)
    username = serializers.CharField(required=False, write_only=True)
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    last_edited_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    outsources = NetworkSerializer(many=True, read_only=True)
    outsources_ids = serializers.ListField(required=False, child=serializers.IntegerField(), allow_null=True, allow_empty=True, write_only=True)
    unaccounted_overtime = serializers.SerializerMethodField()
    closest_plan_approved_id = serializers.IntegerField(required=False, read_only=True)
    total_cost = serializers.FloatField(read_only=True)

    _employee_active_empl = None

    class Meta:
        model = WorkerDay
        fields = ['id', 'employee_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'is_approved', 'worker_day_details', 'is_fact', 'work_hours', 'parent_worker_day_id',
                  'is_outsource', 'is_vacancy', 'shop_code', 'user_login', 'username', 'created_by', 'last_edited_by',
                  'crop_work_hours_by_shop_schedule', 'dttm_work_start_tabel', 'dttm_work_end_tabel', 'is_blocked',
                  'employment_tabel_code', 'outsources', 'outsources_ids', 'unaccounted_overtime',
                  'closest_plan_approved_id', 'cost_per_hour', 'total_cost'] 
        read_only_fields = ['parent_worker_day_id', 'is_blocked', 'closest_plan_approved_id']
        create_only_fields = ['is_fact']
        ref_name = 'WorkerDaySerializer'
        extra_kwargs = {
            'is_fact': {
                'required': False,
            },
            'is_approved': {
                'default': False,
            },
            'is_blocked': {
                'read_only': True,
            },
        }

    @cached_property
    def wd_types_dict(self):
        """
        Закешируем типы для факта на уровне request, чтобы не делать запрос для каждого объекта
        """
        if hasattr(self.context['request'], 'allowed_fact_wd_types'):
            return self.context['request'].allowed_fact_wd_types

        wd_types_dict = {wd.code: wd for wd in WorkerDayType.objects.all()}
        self.context['request'].wd_types_dict = wd_types_dict
        return wd_types_dict

    def validate(self, attrs):
        if self.instance and self.instance.is_approved:
            raise ValidationError({"error": "Нельзя менять подтвержденную версию."})

        if not self.instance:
            attrs['source'] = WorkerDay.SOURCE_FULL_EDITOR
            if (attrs.get('shop_id') is None) and ('shop_code' in attrs) or (attrs.get('employee_id') is None) and ('username' in attrs):
                attrs['source'] = WorkerDay.SOURCE_INTEGRATION
            elif self.context.get('batch'):
                attrs['source'] = WorkerDay.SOURCE_FAST_EDITOR

        is_fact = attrs['is_fact'] if 'is_fact' in attrs else getattr(self.instance, 'is_fact', None)
        wd_type = attrs.pop('type_id')
        wd_type_obj = self.wd_types_dict.get(wd_type)
        attrs['type'] = wd_type_obj
        if is_fact and not wd_type_obj.use_in_fact:
            raise ValidationError({
                "error": "Для фактической неподтвержденной версии можно установить только {}".format(
                    ", ".join([i.name for i in self.wd_types_dict.values() if i.use_in_fact])
                )
            })

        if not wd_type_obj.is_work_hours:
            attrs['is_vacancy'] = False

        shop_id = attrs.get('shop_id')
        if wd_type_obj.is_dayoff:
            attrs['dttm_work_start'] = None
            attrs['dttm_work_end'] = None
            attrs['shop_id'] = None
            attrs.pop('shop_code', None)
        elif not (attrs.get('dttm_work_start') and attrs.get('dttm_work_end')):
            messages = {}
            for k in 'dttm_work_start', 'dttm_work_end':
                if not attrs.get(k):
                    messages[k] = self.error_messages['required']
            raise ValidationError(messages)
        elif attrs['dttm_work_start'] > attrs['dttm_work_end'] or attrs['dt'] != attrs['dttm_work_start'].date():
            self.fail('check_dates')

        if (attrs.get('shop_id') is None) and ('shop_code' in attrs):
            shop_code = attrs.pop('shop_code')
            shops = list(Shop.objects.filter(code=shop_code, network_id=self.context['request'].user.network_id))
            if len(shops) == 1:
                attrs['shop_id'] = shops[0].id
                shop_id = shops[0].id
            else:
                self.fail('no_such_shop_in_network')
        elif attrs.get('shop_id') and not Shop.objects.filter(
                Q(network_id=self.context['request'].user.network_id) |
                Q(network_id__in=NetworkConnect.objects.filter(
                    outsourcing_id=self.context['request'].user.network_id).values_list('client_id', flat=True)),
                id=attrs.get('shop_id'),
        ).exists():
            self.fail('no_such_shop_in_network')

        if (attrs.get('employee_id') is None) and ('username' in attrs):
            username = attrs.pop('username')
            users = list(User.objects.filter(username=username, network_id=self.context['request'].user.network_id))
            if len(users) == 1:
                employee = Employee.objects.filter(user=users[0]).first()
                attrs['employee_id'] = employee.id
            else:
                self.fail('no_user', amount=len(users), username=username)

        if not wd_type == WorkerDay.TYPE_WORKDAY:
            attrs.pop('worker_day_details', None)
            attrs['is_vacancy'] = False
            attrs['is_outsource'] = False
        elif not (attrs.get('worker_day_details')):
            raise ValidationError({
                "worker_day_details": self.error_messages['required']
            })

        if attrs.get('shop_id') and attrs.get('worker_day_details'):
            for wd_details in attrs.get('worker_day_details'):
                if not WorkType.objects.filter(id=wd_details['work_type_id'], shop_id=attrs.get('shop_id')).exists():
                    raise ValidationError({
                        "worker_day_details": self.error_messages['wd_details_shop_mismatch']
                    })

        if attrs.get('employee_id') and attrs.get('employment_id'):
            if not Employment.objects.filter(id=attrs.get('employment_id'), employee_id=attrs.get('employee_id')).exists():
                raise ValidationError({
                    "employment": self.error_messages['user_mismatch']
                })

        if attrs.get('employee_id'):
            outsourcing_network_qs = list(
                NetworkConnect.objects.filter(
                    client=self.context['request'].user.network_id,
                ).values_list('outsourcing_id', flat=True)
            )
            employee_active_empl = Employment.objects.get_active_empl_by_priority(
                extra_q=Q(
                    Q(
                        employee__user__network_id=self.context['request'].user.network_id,
                        shop__network_id=self.context['request'].user.network_id,
                    ) |
                    Q(
                        employee__user__network_id__in=outsourcing_network_qs,
                        shop__network_id__in=outsourcing_network_qs + [self.context['request'].user.network_id],
                    )
                ),
                employee_id=attrs.get('employee_id'),
                dt=attrs.get('dt'),
                priority_shop_id=shop_id,
                priority_employment_id=attrs.get('employment_id'),
            ).first()
            if not employee_active_empl:
                raise self.fail('no_active_employments')

            attrs['employment_id'] = employee_active_empl.id
            self._employee_active_empl = employee_active_empl

            if is_fact and not wd_type_obj.is_dayoff:
                closest_plan_approved = WorkerDay.get_closest_plan_approved_q(
                    employee_id=attrs['employee_id'],
                    dt=attrs['dt'],
                    dttm_work_start=attrs['dttm_work_start'],
                    dttm_work_end=attrs['dttm_work_end'],
                    delta_in_secs=self.context['request'].user.network.set_closest_plan_approved_delta_for_manual_fact,
                ).only('id').first()
                if closest_plan_approved:
                    attrs['closest_plan_approved_id'] = closest_plan_approved.id

        outsources_ids = attrs.pop('outsources_ids', []) or []
        if attrs.get('is_outsource'):
            if not attrs.get('is_vacancy'):
                raise ValidationError(self.error_messages['outsource_only_vacancy'])
            outsources = list(Network.objects.filter(
                id__in=outsources_ids,
                clients__id=self.context['request'].user.network_id,
            ))
            if len(outsources) == 0:
                raise ValidationError(self.error_messages['outsources_not_specified'])
            attrs['outsources'] = outsources
        else:
            attrs['outsources'] = []

        return attrs

    def _create_update_clean(self, validated_data, instance=None):
        employee_id = validated_data.get('employee_id', instance.employee_id if instance else None)
        if employee_id:
            validated_data['is_vacancy'] = validated_data.get('is_vacancy') \
                or not getattr(self._employee_active_empl, 'is_equal_shops', True)

    def _run_transaction_checks(self, employee_id, dt, is_fact, is_approved):
        WorkerDay.check_work_time_overlap(
            employee_id=employee_id, dt=dt, is_fact=is_fact, is_approved=is_approved, exc_cls=ValidationError)
        WorkerDay.check_multiple_workday_types(
            employee_id=employee_id, dt=dt, is_fact=is_fact, is_approved=is_approved, exc_cls=ValidationError)

    def create(self, validated_data):
        with transaction.atomic():
            self._create_update_clean(validated_data)

            details = validated_data.pop('worker_day_details', None)
            outsources = validated_data.pop('outsources', None)
            canceled_vacancies = WorkerDay.objects.filter(
                is_vacancy=True,
                dt=validated_data.get('dt'),
                shop_id=validated_data.get('shop_id'),
                worker_day_details__work_type_id__in=list(map(lambda x: x['work_type_id'], details)) if details else [],
                canceled=True,
                is_fact=False,
                is_approved=True,
                employee_id__isnull=True,
            )
            # при создании вакансии вручную пробуем "востанавить" удаленную вакансию, которая была создана автоматом
            if validated_data.get('is_vacancy') and not validated_data.get('is_fact')\
                and not validated_data.get('employee_id') and canceled_vacancies.exists():
                worker_day = canceled_vacancies.first()
                WorkerDay.objects.filter(
                    id=worker_day.id,
                ).update(
                    canceled=False,
                    **validated_data,
                )
                worker_day.refresh_from_db()
            else:
                worker_day = WorkerDay.objects.create(
                    **validated_data,
                )
            if details:
                WorkerDayCashboxDetails.objects.filter(worker_day=worker_day).delete()
                for wd_detail in details:
                    WorkerDayCashboxDetails.objects.create(worker_day=worker_day, **wd_detail)
            
            if outsources:
                worker_day.outsources.set(outsources)

            self._run_transaction_checks(
                employee_id=worker_day.employee_id, dt=worker_day.dt,
                is_fact=worker_day.is_fact, is_approved=worker_day.is_approved,
            )

            return worker_day

    def update(self, instance, validated_data):
        with transaction.atomic():
            details = validated_data.pop('worker_day_details', [])
            outsources = validated_data.pop('outsources', [])
            validated_data.pop('created_by', None)
            WorkerDayCashboxDetails.objects.filter(worker_day=instance).delete()
            instance.outsources.set(outsources)
            for wd_detail in details:
                WorkerDayCashboxDetails.objects.create(worker_day=instance, **wd_detail)

            self._create_update_clean(validated_data, instance=instance)

            res = super().update(instance, validated_data)

            self._run_transaction_checks(
                employee_id=instance.employee_id, dt=instance.dt,
                is_fact=instance.is_fact, is_approved=instance.is_approved,
            )

            return res

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
                    raise serializers.ValidationError({field: self.error_messages['required']})
        return data

    def get_unaccounted_overtime(self, obj):
        return self.unaccounted_overtime_getter(obj)


class WorkerDayWithParentSerializer(WorkerDaySerializer):
    parent_worker_day_id = serializers.IntegerField()


class VacancySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    employee_id = serializers.IntegerField()
    worker_day_details = WorkerDayCashboxDetailsListSerializer(many=True, required=False)
    is_fact = serializers.BooleanField()
    is_approved = serializers.BooleanField()
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    dt = serializers.DateField()
    type = serializers.CharField(source='type_id')
    is_outsource = serializers.BooleanField()
    avatar = serializers.SerializerMethodField('get_avatar_url')
    worker_shop = serializers.IntegerField(required=False, default=None)
    user_network_id = serializers.IntegerField(required=False)
    outsources = NetworkListSerializer(many=True, read_only=True)
    shop = ShopListSerializer()
    comment = serializers.CharField(required=False)
    cost_per_hour = serializers.DecimalField(None, None)
    total_cost = serializers.FloatField(read_only=True)

    def get_avatar_url(self, obj) -> str:
        if obj.employee_id and obj.employee.user_id and obj.employee.user.avatar:
            return obj.employee.user.avatar.url
        return None


class ChangeListSerializer(serializers.Serializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
    }
    shop_id = serializers.IntegerField(required=False)
    employee_id = serializers.IntegerField(required=False)
    type = serializers.CharField(source='type_id')
    tm_work_start = serializers.TimeField(required=False)
    tm_work_end = serializers.TimeField(required=False)
    cashbox_details = WorkerDayCashboxDetailsSerializer(many=True, required=False)
    is_vacancy = serializers.BooleanField(default=False)
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    outsources = serializers.ListField(required=False, child=serializers.IntegerField(), allow_null=True, allow_empty=True, write_only=True)
    # 0 - ПН, 6 - ВС
    days_of_week = serializers.ListField(required=False, child=serializers.IntegerField(), allow_null=True, allow_empty=True, write_only=True)
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    def _generate_dates(self, dt_from, dt_to, days_of_week=[]):
        dates = pd.date_range(dt_from, dt_to)
        if days_of_week:
            dates = dates[dates.dayofweek.isin(days_of_week)]
        return list(dates.date)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)

        wd_types_dict = self.context.get('wd_types_dict') or WorkerDayType.get_wd_types_dict()
        if self.validated_data['is_vacancy']:
            self.validated_data['type_id'] = WorkerDay.TYPE_WORKDAY
            self.validated_data['outsources'] = Network.objects.filter(id__in=(self.validated_data.get('outsources') or []))
        else:
            if wd_types_dict.get(self.validated_data['type_id']).is_dayoff:
                self.validated_data['shop_id'] = None 
            self.validated_data['outsources'] = []
        if not wd_types_dict.get(self.validated_data['type_id']).is_dayoff:
            if not self.validated_data.get('tm_work_start'):
                raise FieldError(self.error_messages['required'], 'tm_work_start')
            if not self.validated_data.get('tm_work_end'):
                raise FieldError(self.error_messages['required'], 'tm_work_end')
            if not self.validated_data.get('shop_id'):
                raise FieldError(self.error_messages['required'], 'shop_id')
            if not self.validated_data.get('cashbox_details'):
                raise FieldError(self.error_messages['required'], 'cashbox_details')
            if not self.validated_data.get('is_vacancy') and not self.validated_data.get('employee_id'):
                raise FieldError(self.error_messages['required'], 'employee_id')
        else:
            if not self.validated_data.get('employee_id'):
                raise FieldError(self.error_messages['required'], 'employee_id')
            self.validated_data['cashbox_details'] = []
        if self.validated_data['dt_from'] > self.validated_data['dt_to']:
            self.fail('check_dates')
        self.validated_data['dates'] = self._generate_dates(
            self.validated_data['dt_from'], 
            self.validated_data['dt_to'], 
            days_of_week=self.validated_data.get('days_of_week', [])
        )
        return True


class ChangeRangeSerializer(serializers.Serializer):
    #is_fact = serializers.BooleanField()
    is_approved = serializers.BooleanField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    worker = serializers.CharField(allow_null=False, allow_blank=False)  # табельный номер

    def __init__(self, *args, **kwargs):
        super(ChangeRangeSerializer, self).__init__(*args, **kwargs)
        self.fields['type'] = serializers.PrimaryKeyRelatedField(queryset=WorkerDayType.objects.filter(is_dayoff=True))

    def validate(self, data):
        if not data['dt_to'] >= data['dt_from']:
            raise serializers.ValidationError("dt_to must be greater than or equal to dt_from")

        return data


class ChangeRangeListSerializer(serializers.Serializer):
    def __init__(self, *args, **kwargs):
        super(ChangeRangeListSerializer, self).__init__(*args, **kwargs)
        self.fields['ranges'] = ChangeRangeSerializer(many=True, context=self.context)


class CopyApprovedSerializer(serializers.Serializer):
    TYPE_PLAN_TO_PLAN = 'PP'
    TYPE_PLAN_TO_FACT = 'PF'
    TYPE_FACT_TO_FACT = 'FF'
    TYPES = [
        (TYPE_PLAN_TO_PLAN, 'План в план'),
        (TYPE_PLAN_TO_FACT, 'План в факт'),
        (TYPE_FACT_TO_FACT, 'Факт в факт'),
    ]
    SOURCES = {
        TYPE_PLAN_TO_PLAN: WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_PLAN,
        TYPE_PLAN_TO_FACT: WorkerDay.SOURCE_COPY_APPROVED_PLAN_TO_FACT,
        TYPE_FACT_TO_FACT: WorkerDay.SOURCE_COPY_APPROVED_FACT_TO_FACT,
    }

    employee_ids = serializers.ListField(child=serializers.IntegerField())
    dates = serializers.ListField(child=serializers.DateField())
    type = serializers.ChoiceField(choices=TYPES, default=TYPE_PLAN_TO_PLAN)
    to_fact = serializers.BooleanField(default=False)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        attrs['source'] = self.SOURCES[attrs['type']]

        return attrs


class DuplicateSrializer(serializers.Serializer):
    default_error_messages = {
        'not_exist': _("Invalid pk \"{pk_value}\" - object does not exist.")
    }
    to_employee_id = serializers.IntegerField()
    from_employee_id = serializers.IntegerField()
    from_dates = serializers.ListField(child=serializers.DateField(format=QOS_DATE_FORMAT))
    to_dates = serializers.ListField(child=serializers.DateField(format=QOS_DATE_FORMAT))
    is_approved = serializers.BooleanField(default=False)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if not Employee.objects.filter(id=self.data['to_employee_id']).exists():
            raise ValidationError({'to_employee_id': self.error_messages['not_exist'].format(pk_value=self.validated_data['to_employee_id'])})
        if not Employee.objects.filter(id=self.data['from_employee_id']).exists():
            raise ValidationError({'from_employee_id': self.error_messages['not_exist'].format(pk_value=self.validated_data['from_employee_id'])})
        return True


class DeleteWorkerDaysSerializer(serializers.Serializer):
    employee_ids = serializers.ListField(child=serializers.IntegerField())
    dates = serializers.ListField(child=serializers.DateField())
    is_fact = serializers.BooleanField(default=False)
    exclude_created_by = serializers.BooleanField(default=True)
    shop_id = serializers.IntegerField(required=False)


class ExchangeSerializer(serializers.Serializer):
    default_error_messages = {
        'not_exist': _("Invalid pk \"{pk_value}\" - object does not exist.")
    }

    employee1_id = serializers.IntegerField()
    employee2_id = serializers.IntegerField()
    dates = serializers.ListField(child=serializers.DateField(format=QOS_DATE_FORMAT))

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        for key in ['employee1_id', 'employee2_id']:
            if not Employee.objects.filter(id=self.validated_data[key]).exists():
                raise ValidationError({key: self.error_messages['not_exist'].format(pk_value=self.validated_data[key])})


class CopyRangeSerializer(serializers.Serializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
        'check_periods': _('Start of first period can\'t be greater than start of second period'),
    }

    employee_ids = serializers.ListField(child=serializers.IntegerField())
    from_copy_dt_from = serializers.DateField()
    from_copy_dt_to = serializers.DateField()
    to_copy_dt_from = serializers.DateField()
    to_copy_dt_to = serializers.DateField()
    is_approved = serializers.BooleanField(default=False)
    worker_day_types = serializers.ListField(child=serializers.CharField(), default=['W', 'H', 'M'])

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if self.validated_data['from_copy_dt_from'] > self.validated_data['from_copy_dt_to'] or\
        self.validated_data['to_copy_dt_from'] > self.validated_data['to_copy_dt_to']:
            raise serializers.ValidationError(self.error_messages['check_dates'])

        if self.validated_data['from_copy_dt_from'] > self.validated_data['to_copy_dt_from']:
            raise serializers.ValidationError(self.error_messages['check_periods'])

        self.validated_data['from_dates'] = [
            self.validated_data['from_copy_dt_from'] + timedelta(i)
            for i in range((self.validated_data['from_copy_dt_to'] - self.validated_data['from_copy_dt_from']).days + 1)
        ]

        self.validated_data['to_dates'] = [
            self.validated_data['to_copy_dt_from'] + timedelta(i)
            for i in range((self.validated_data['to_copy_dt_to'] - self.validated_data['to_copy_dt_from']).days + 1)
        ]

        return True


class UploadTimetableSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    file = serializers.FileField()


class GenerateUploadTimetableExampleSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT)
    employee_id__in = serializers.ListField(child=serializers.IntegerField(), required=False)
    is_fact = serializers.BooleanField(default=False)
    is_approved = serializers.BooleanField(default=False)


class DownloadSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    is_approved = serializers.BooleanField(default=True)
    inspection_version = serializers.BooleanField(default=False)
    shop_id = serializers.IntegerField()
    on_print = serializers.BooleanField(default=False)


class DownloadTabelSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT)
    shop_id = serializers.IntegerField()
    convert_to = serializers.ChoiceField(required=False, choices=['pdf', 'xlsx'], default='xlsx')
    tabel_type = serializers.ChoiceField(
        required=False, choices=TimesheetItem.TIMESHEET_TYPE_CHOICES, default=TimesheetItem.TIMESHEET_TYPE_FACT)


class BlockOrUnblockWorkerDaySerializer(serializers.ModelSerializer):
    worker_username = serializers.CharField(required=False)
    shop_code = serializers.CharField(required=False)

    class Meta:
        model = WorkerDay
        fields = (
            'employee_id',
            'worker_username',
            'shop_id',
            'shop_code',
            'dt',
            'is_fact',
        )

    def validate(self, attrs):
        if (attrs.get('shop_id') is None) and ('shop_code' in attrs):
            shop_code = attrs.pop('shop_code')
            shops = list(Shop.objects.filter(code=shop_code, network_id=self.context['request'].user.network_id))
            if len(shops) == 1:
                attrs['shop_id'] = shops[0].id
            else:
                raise NotFound(detail=f'Подразделение с кодом "{shop_code}" не найдено')

        if (attrs.get('employee_id') is None) and ('worker_username' in attrs):
            username = attrs.pop('worker_username')
            users = list(User.objects.filter(username=username, network_id=self.context['request'].user.network_id))
            if len(users) == 1:
                employee = Employee.objects.filter(user=users[0]).first()
                attrs['employee_id'] = employee.id
            else:
                raise NotFound(detail=f'Пользователь "{username}" не найден')

        return attrs


class BlockOrUnblockWorkerDayWrapperSerializer(serializers.Serializer):
    worker_days = BlockOrUnblockWorkerDaySerializer(many=True)


class RecalcWdaysSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT)
    employee_id__in = serializers.ListField(child=serializers.IntegerField(), required=False)

class OvertimesUndertimesReportSerializer(serializers.Serializer):
    employee_id__in = serializers.CharField(required=False)
    shop_id = serializers.IntegerField(required=False)

    def is_valid(self, *atgs, **kwargs):
        super().is_valid(*atgs, **kwargs)
        if not self.validated_data.get('shop_id') and not self.validated_data.get('employee_id__in'):
            raise ValidationError(_('Shop or employees should be defined.'))
        if self.validated_data.get('employee_id__in'):
            self.validated_data['employee_id__in'] = self.validated_data['employee_id__in'].split(',')

class ConfirmVacancyToWorkerSerializer(serializers.Serializer):
    default_error_messages = {
        "employee_not_in_subordinates": _("Employee {employee} is not your subordinate."),
        "no_such_user_in_network": _("There is no such user in your network."),
    }

    employee_id = serializers.IntegerField()
    user_id = serializers.IntegerField()

    def validate(self, attrs):
        user = self.context['request'].user
        attrs['user'] = User.objects.filter(id=attrs['user_id'], network_id=user.network_id).first()
        if not attrs['user']:
            raise ValidationError(self.error_messages["no_such_user_in_network"])
        employee_id = attrs['employee_id']
        
        if not WorkerDay._has_group_permissions(user, employee_id):
            raise PermissionDenied(
                self.error_messages['employee_not_in_subordinates'].format(
                employee=attrs['user'].fio),
            )
        return attrs
