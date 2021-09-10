from datetime import timedelta
from src.base.exceptions import FieldError
import pandas as pd

from django.db import transaction
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, NotFound

from src.base.models import Employment, User, Shop, Employee, Network
from src.base.models import NetworkConnect
from src.base.serializers import NetworkListSerializer, UserShorSerializer, NetworkSerializer
from src.base.shop.serializers import ShopListSerializer, ShopSerializer
from src.conf.djconfig import QOS_DATE_FORMAT
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
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
        child=serializers.ChoiceField(choices=WorkerDay.TYPES),
        # required=True,
        default=WorkerDay.TYPES_USED,  # временно для Ортеки
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

def serialize_worker_day(wd: WorkerDay, request):
    work_hours = None
    if isinstance(wd.work_hours, timedelta):
        work_hours = wd.rounded_work_hours
    work_hours = wd.work_hours
    return {
        'id': wd.id,
        'worker_id': wd.employee.user_id,
        'employee_id': wd.employee_id,
        'shop_id': wd.shop_id,
        'employment_id': wd.employment_id,
        'type': wd.type,
        'dt': wd.dt,
        'dttm_work_start': wd.dttm_work_start,
        'dttm_work_end': wd.dttm_work_end,
        'dttm_work_start_tabel': wd.dttm_work_start_tabel,
        'dttm_work_end_tabel': wd.dttm_work_end_tabel,
        'comment': wd.comment,
        'is_approved': wd.is_approved,
        'is_fact': wd.is_fact,
        'work_hours': work_hours,
        'shop_code': getattr(wd, 'shop_code', None),
        'user_login': getattr(wd, 'user_login', None),
        'employment_tabel_code': getattr(wd, 'employment_tabel_code', None),
        'created_by_id': wd.created_by_id,
        'dttm_modified': wd.dttm_modified,
        'is_blocked': wd.is_blocked,
        'unaccounted_overtime': UnaccountedOvertimeMixin().unaccounted_overtime_getter(wd),
        'worker_day_details': WorkerDayCashboxDetailsListSerializer(wd.worker_day_details_list, many=True).data,
        'outsources': NetworkListSerializer(wd.outsources_list, many=True).data,
        'last_edited_by': UserShorSerializer(wd.last_edited_by).data,
    }

class WorkerDayListSerializer(serializers.Serializer, UnaccountedOvertimeMixin):
    id = serializers.IntegerField()
    worker_id = serializers.IntegerField(source='employee.user_id')
    employee_id = serializers.IntegerField()
    shop_id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    type = serializers.CharField()
    dt = serializers.DateField()
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    dttm_work_start_tabel = serializers.DateTimeField(default=None)
    dttm_work_end_tabel = serializers.DateTimeField(default=None)
    comment = serializers.CharField()
    is_approved = serializers.BooleanField()
    worker_day_details = WorkerDayCashboxDetailsListSerializer(many=True)
    outsources = NetworkListSerializer(many=True, required=False)
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
    type = serializers.CharField(required=True)
    shop_code = serializers.CharField(required=False)
    user_login = serializers.CharField(required=False, read_only=True)
    employment_tabel_code = serializers.CharField(required=False, read_only=True)
    username = serializers.CharField(required=False, write_only=True)
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    last_edited_by = serializers.HiddenField(default=serializers.CurrentUserDefault())
    outsources = NetworkSerializer(many=True, read_only=True)
    outsources_ids = serializers.ListField(required=False, child=serializers.IntegerField(), allow_null=True, allow_empty=True, write_only=True)
    unaccounted_overtime = serializers.SerializerMethodField()

    class Meta:
        model = WorkerDay
        fields = ['id', 'employee_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'is_approved', 'worker_day_details', 'is_fact', 'work_hours', 'parent_worker_day_id',
                  'is_outsource', 'is_vacancy', 'shop_code', 'user_login', 'username', 'created_by', 'last_edited_by',
                  'crop_work_hours_by_shop_schedule', 'dttm_work_start_tabel', 'dttm_work_end_tabel', 'is_blocked',
                  'employment_tabel_code', 'outsources', 'outsources_ids', 'unaccounted_overtime']
        read_only_fields = ['work_hours', 'parent_worker_day_id', 'is_blocked']
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

    def validate(self, attrs):
        if self.instance and self.instance.is_approved:
            raise ValidationError({"error": "Нельзя менять подтвержденную версию."})

        is_fact = attrs['is_fact'] if 'is_fact' in attrs else getattr(self.instance, 'is_fact', None)
        wd_type = attrs['type']

        if is_fact and wd_type not in WorkerDay.TYPES_WITH_TM_RANGE + (WorkerDay.TYPE_EMPTY,):
            raise ValidationError({
                "error": "Для фактической неподтвержденной версии можно установить только 'Рабочий день',"
                         " 'Обучение', 'Командировка' и 'НД'."
            })

        if not WorkerDay.is_type_with_tm_range(wd_type):
            attrs['dttm_work_start'] = None
            attrs['dttm_work_end'] = None
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
            else:
                self.fail('no_shop', amount=len(shops), code=shop_code)
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
            wdays_qs = WorkerDay.objects_with_excluded.filter(
                employee_id=employee_id,
                dt=validated_data.get('dt'),
                is_approved=validated_data.get(
                    'is_approved',
                    instance.is_approved if instance else WorkerDay._meta.get_field('is_approved').default,
                ),
                is_fact=validated_data.get(
                    'is_fact', instance.is_fact if instance else WorkerDay._meta.get_field('is_fact').default),
            )
            if instance:
                wdays_qs = wdays_qs.exclude(id=instance.id)
            wdays_qs.delete()

            outsourcing_network_qs = NetworkConnect.objects.filter(
                client=self.context['request'].user.network_id,
            ).values_list('outsourcing_id', flat=True)
            employee_active_empl = Employment.objects.get_active_empl_by_priority(
                extra_q=Q(
                    Q(
                        employee__user__network_id=self.context['request'].user.network_id,
                        shop__network_id=self.context['request'].user.network_id,
                    ) |
                    Q(
                        employee__user__network_id__in=outsourcing_network_qs,
                        shop__network_id__in=outsourcing_network_qs,
                    )
                ),
                employee_id=employee_id,
                dt=validated_data.get('dt'),
                priority_shop_id=validated_data.get('shop_id'),
                priority_employment_id=validated_data.get('employment_id'),
            ).first()

            if not employee_active_empl:
                raise self.fail('no_active_employments')

            validated_data['employment_id'] = employee_active_empl.id
            validated_data['is_vacancy'] = validated_data.get('is_vacancy') \
                or not employee_active_empl.is_equal_shops

    def _check_overlap(self, employee_id, dt):
        WorkerDay.check_work_time_overlap(employee_id=employee_id, dt=dt, exc_cls=ValidationError)

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
            elif validated_data.get('employee_id'):
                worker_day, _created = WorkerDay.objects.update_or_create(
                    dt=validated_data.get('dt'),
                    employee_id=validated_data.get('employee_id'),
                    employment_id=validated_data.get('employment_id'),
                    is_fact=validated_data.get('is_fact'),
                    is_approved=validated_data.get('is_approved'),
                    defaults=validated_data,
                )
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

            self._check_overlap(employee_id=worker_day.employee_id, dt=worker_day.dt)

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

            self._check_overlap(employee_id=instance.employee_id, dt=instance.dt)

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
    type = serializers.CharField()
    is_outsource = serializers.BooleanField()
    avatar = serializers.SerializerMethodField('get_avatar_url')
    worker_shop = serializers.IntegerField(required=False, default=None)
    user_network_id = serializers.IntegerField(required=False)
    outsources = NetworkListSerializer(many=True, read_only=True)
    shop = ShopListSerializer()

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
    type = serializers.CharField()
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
        if self.validated_data['is_vacancy']:
            self.validated_data['type'] = WorkerDay.TYPE_WORKDAY
            self.validated_data['outsources'] = Network.objects.filter(id__in=self.validated_data.get('outsources', []))
        else:
            if not WorkerDay.is_type_with_tm_range(self.validated_data['type']):
                self.validated_data['shop_id'] = None 
            self.validated_data['outsources'] = []
        if WorkerDay.is_type_with_tm_range(self.validated_data['type']):
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
    is_fact = serializers.BooleanField()
    is_approved = serializers.BooleanField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    type = serializers.ChoiceField(
        choices=[
            WorkerDay.TYPE_MATERNITY,
            WorkerDay.TYPE_MATERNITY_CARE,
            WorkerDay.TYPE_SICK,
            WorkerDay.TYPE_VACATION,
        ]
    )
    worker = serializers.CharField(allow_null=False, allow_blank=False)  # табельный номер

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

    employee_ids = serializers.ListField(child=serializers.IntegerField())
    dates = serializers.ListField(child=serializers.DateField())
    type = serializers.ChoiceField(choices=TYPES, default=TYPE_PLAN_TO_PLAN)
    to_fact = serializers.BooleanField(default=False)


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


class DownloadTabelSerializer(serializers.Serializer):
    TYPE_FACT = 'F'
    TYPE_MAIN = 'M'
    TYPE_ADDITIONAL = 'A'

    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT)
    shop_id = serializers.IntegerField()
    convert_to = serializers.ChoiceField(required=False, choices=['pdf', 'xlsx'], default='xlsx')
    tabel_type = serializers.ChoiceField(required=False, choices=[TYPE_FACT, TYPE_MAIN, TYPE_ADDITIONAL], default=TYPE_FACT)


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
