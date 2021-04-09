from datetime import timedelta

from django.db import transaction
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, NotFound

from src.base.models import Employment, User, Shop
from src.base.shop.serializers import ShopSerializer
from src.base.serializers import UserListSerializer
from src.conf.djconfig import QOS_DATE_FORMAT
from src.timetable.models import (
    WorkerDay,
    WorkerDayCashboxDetails,
    WorkType,
)
from src.util.models_converter import Converter


class RequestApproveSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField(required=True)
    comment = serializers.CharField(allow_blank=True, required=False)


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


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    work_type_id = serializers.IntegerField(required=True)

    class Meta:
        model = WorkerDayCashboxDetails
        fields = ['id', 'work_type_id', 'work_part']


class WorkerDayCashboxDetailsListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    work_type_id = serializers.IntegerField()
    work_part = serializers.FloatField()


class WorkerDayListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    worker_id = serializers.IntegerField()
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
    is_fact = serializers.BooleanField()
    work_hours = serializers.SerializerMethodField()
    parent_worker_day_id = serializers.IntegerField()
    shop_code = serializers.CharField(required=False, read_only=True)
    user_login = serializers.CharField(required=False, read_only=True)
    employment_tabel_code = serializers.CharField(required=False, read_only=True)
    created_by_id = serializers.IntegerField(read_only=True)
    last_edited_by = UserListSerializer(read_only=True)
    dttm_modified = serializers.DateTimeField(read_only=True)
    is_blocked = serializers.BooleanField(read_only=True)

    def get_work_hours(self, obj) -> float:
        if isinstance(obj.work_hours, timedelta):
            return obj.rounded_work_hours

        return obj.work_hours


class WorkerDaySerializer(serializers.ModelSerializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
        'worker_day_exist': _("Worker day already exist."),
        'worker_day_intercept': _("Worker day intercepts with another: {shop_name}, {work_start}, {work_end}."),
        "no_user": _("There is {amount} models of user with username: {username}."),
        "wd_details_shop_mismatch": _("Shop in work type and in work day must match."),
        "user_mismatch": _("User in employment and in worker day must match."),
        "no_active_employments": _(
            "Can't create a working day in the schedule, since the user is not employed during this period"),
    }

    worker_day_details = WorkerDayCashboxDetailsSerializer(many=True, required=False)
    worker_id = serializers.IntegerField(required=False, allow_null=True)
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

    class Meta:
        model = WorkerDay
        fields = ['id', 'worker_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'is_approved', 'worker_day_details', 'is_fact', 'work_hours', 'parent_worker_day_id',
                  'is_outsource', 'is_vacancy', 'shop_code', 'user_login', 'username', 'created_by', 'last_edited_by',
                  'crop_work_hours_by_shop_schedule', 'dttm_work_start_tabel', 'dttm_work_end_tabel', 'is_blocked',
                  'employment_tabel_code']
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
            }
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
        elif attrs['dttm_work_start'] > attrs['dttm_work_end'] or attrs['dt'] != attrs['dttm_work_start'].date() or \
                attrs['dt'] != attrs['dttm_work_start'].date():
            self.fail('check_dates')

        if (attrs.get('shop_id') is None) and ('shop_code' in attrs):
            shop_code = attrs.pop('shop_code')
            shops = list(Shop.objects.filter(code=shop_code, network_id=self.context['request'].user.network_id))
            if len(shops) == 1:
                attrs['shop_id'] = shops[0].id
            else:
                self.fail('no_shop', amount=len(shops), code=shop_code)

        if (attrs.get('worker_id') is None) and ('username' in attrs):
            username = attrs.pop('username')
            users = list(User.objects.filter(username=username, network_id=self.context['request'].user.network_id))
            if len(users) == 1:
                attrs['worker_id'] = users[0].id
            else:
                self.fail('no_user', amount=len(users), username=username)

        if not wd_type == WorkerDay.TYPE_WORKDAY:
            attrs.pop('worker_day_details', None)
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

        if attrs.get('worker_id') and attrs.get('employment_id'):
            if not Employment.objects.filter(id=attrs.get('employment_id'), user_id=attrs.get('worker_id')).exists():
                raise ValidationError({
                    "employment": self.error_messages['user_mismatch']
                })

        # if is_fact and wd_type == WorkerDay.TYPE_WORKDAY \
        #         and attrs.get('worker_id') and attrs.get('shop_id') and attrs.get('created_by'):
        #     similar_plan_exists = WorkerDay.objects.filter(
        #         type=WorkerDay.TYPE_WORKDAY,
        #         is_fact=False,
        #         is_approved=True,
        #         dt=attrs.get('dt'),
        #         worker_id=attrs.get('worker_id'),
        #         shop_id=attrs.get('shop_id'),
        #     ).exists()
        #     if not similar_plan_exists:
        #         raise ValidationError({
        #             "error": "Не существует рабочего дня в плановом подтвержденном графике. "
        #                      "Необходимо создать и подтвердить рабочий день в плановом графике, "
        #                      "или проверить, что магазины в плановом и фактическом графиках совпадают."
        #         })

        return attrs

    def _create_update_clean(self, validated_data, instance=None):
        worker_id = validated_data.get('worker_id', instance.worker_id if instance else None)
        if worker_id:
            wdays_qs = WorkerDay.objects_with_excluded.filter(
                worker_id=worker_id,
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

            if validated_data.get('type') in WorkerDay.TYPES_WITH_TM_RANGE:
                worker_active_empl = Employment.objects.get_active_empl_for_user(
                    network_id=self.context['request'].user.network_id,
                    user_id=worker_id,
                    dt=validated_data.get('dt'),
                    priority_shop_id=validated_data.get('shop_id'),
                    priority_employment_id=validated_data.get('employment_id'),
                ).first()

                if not worker_active_empl:
                    raise self.fail('no_active_employments')

                validated_data['employment_id'] = worker_active_empl.id
                validated_data['is_vacancy'] = validated_data.get('is_vacancy') \
                    or not worker_active_empl.is_equal_shops

    def create(self, validated_data):
        with transaction.atomic():
            self._create_update_clean(validated_data)

            details = validated_data.pop('worker_day_details', None)
            worker_day, _created = WorkerDay.objects.update_or_create(
                dt=validated_data.get('dt'),
                worker_id=validated_data.get('worker_id'),
                is_fact=validated_data.get('is_fact'),
                is_approved=validated_data.get('is_approved'),
                defaults=validated_data,
            )
            if details:
                WorkerDayCashboxDetails.objects.filter(worker_day=worker_day).delete()
                for wd_detail in details:
                    WorkerDayCashboxDetails.objects.create(worker_day=worker_day, **wd_detail)

            return worker_day

    def update(self, instance, validated_data):
        with transaction.atomic():
            details = validated_data.pop('worker_day_details', [])
            validated_data.pop('created_by', None)
            WorkerDayCashboxDetails.objects.filter(worker_day=instance).delete()
            for wd_detail in details:
                WorkerDayCashboxDetails.objects.create(worker_day=instance, **wd_detail)

            self._create_update_clean(validated_data, instance=instance)

            return super().update(instance, validated_data)

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


class WorkerDayWithParentSerializer(WorkerDaySerializer):
    parent_worker_day_id = serializers.IntegerField()


class VacancySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    worker_id = serializers.IntegerField()
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

    def __init__(self, *args, **kwargs):
        super(VacancySerializer, self).__init__(*args, **kwargs)
        self.fields['shop'] = ShopSerializer(context=self.context)

    def get_avatar_url(self, obj) -> str:
        if obj.worker_id and obj.worker.avatar:
            return obj.worker.avatar.url
        return None


class ListChangeSrializer(serializers.Serializer):
    default_error_messages = {
        "invalid_dt_change_list": _("Wrong dates format.")}
    shop_id = serializers.IntegerField()
    workers = serializers.JSONField()
    type = serializers.CharField()
    tm_work_start = serializers.TimeField(required=False)
    tm_work_end = serializers.TimeField(required=False)
    work_type = serializers.IntegerField(required=False)
    comment = serializers.CharField(max_length=128, required=False)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if WorkerDay.is_type_with_tm_range(self.validated_data['type']):
            if self.validated_data.get('tm_work_start') is None:
                self.tm_work_start.fail('required')
            if self.validated_data.get('tm_work_end') is None:
                self.tm_work_end.fail('required')

            workers = self.validated_data.get('workers')
            for key, value in workers.items():
                try:
                    workers[key] = list(map(lambda x: Converter.parse_date(x), value))
                except:
                    raise ValidationError({'error': self.error_messages['invalid_dt_change_list']})


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

    def __init__(self, *args, **kwargs):
        super(ChangeRangeSerializer, self).__init__(*args, **kwargs)
        if self.context.get('request'):
            self.fields['worker'] = serializers.SlugRelatedField(
                slug_field='tabel_code', queryset=User.objects.filter(network=self.context['request'].user.network))

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

    worker_ids = serializers.ListField(child=serializers.IntegerField())
    dates = serializers.ListField(child=serializers.DateField())
    type = serializers.ChoiceField(choices=TYPES, default=TYPE_PLAN_TO_PLAN)
    to_fact = serializers.BooleanField(default=False)


class DuplicateSrializer(serializers.Serializer):
    default_error_messages = {
        'not_exist': _("Invalid pk \"{pk_value}\" - object does not exist.")
    }
    to_worker_id = serializers.IntegerField()
    from_workerday_ids = serializers.ListField(child=serializers.IntegerField(), allow_null=False, allow_empty=False)
    to_dates = serializers.ListField(child=serializers.DateField(format=QOS_DATE_FORMAT))

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if not User.objects.filter(id=self.data['to_worker_id']).exists():
            raise ValidationError({'to_worker_id': self.error_messages['not_exist'].format(pk_value=self.validated_data['to_worker_id'])})
        return True


class DeleteWorkerDaysSerializer(serializers.Serializer):
    worker_ids = serializers.ListField(child=serializers.IntegerField())
    dates = serializers.ListField(child=serializers.DateField())
    is_fact = serializers.BooleanField(default=False)
    exclude_created_by = serializers.BooleanField(default=True)


class ExchangeSerializer(serializers.Serializer):
    default_error_messages = {
        'not_exist': _("Invalid pk \"{pk_value}\" - object does not exist.")
    }

    worker1_id = serializers.IntegerField()
    worker2_id = serializers.IntegerField()
    dates = serializers.ListField(child=serializers.DateField(format=QOS_DATE_FORMAT))

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        for key in ['worker1_id', 'worker2_id']:
            if not User.objects.filter(id=self.validated_data[key]).exists():
                raise ValidationError({key: self.error_messages['not_exist'].format(pk_value=self.validated_data[key])})


class CopyRangeSerializer(serializers.Serializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
        'check_periods': _('Start of first period can\'t be greater than start of second period'),
    }

    worker_ids = serializers.ListField(child=serializers.IntegerField())
    from_copy_dt_from = serializers.DateField()
    from_copy_dt_to = serializers.DateField()
    to_copy_dt_from = serializers.DateField()
    to_copy_dt_to = serializers.DateField()
    is_approved = serializers.BooleanField(default=True)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        if self.validated_data['from_copy_dt_from'] > self.validated_data['from_copy_dt_to'] or\
        self.validated_data['to_copy_dt_from'] > self.validated_data['to_copy_dt_to']:
            raise serializers.ValidationError(self.error_messages['check_dates'])

        if self.validated_data['from_copy_dt_from'] > self.validated_data['to_copy_dt_from']:
            raise serializers.ValidationError(self.error_messages['check_periods'])
        
        return True


class UploadTimetableSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    file = serializers.FileField()


class DownloadSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    is_approved = serializers.BooleanField(default=True)
    inspection_version = serializers.BooleanField(default=False)
    shop_id = serializers.IntegerField()


class DownloadTabelSerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT)
    shop_id = serializers.IntegerField()
    convert_to = serializers.ChoiceField(required=False, choices=['pdf', 'xlsx'], default='xlsx')


class BlockOrUnblockWorkerDaySerializer(serializers.ModelSerializer):
    worker_username = serializers.CharField(required=False)
    shop_code = serializers.CharField(required=False)

    class Meta:
        model = WorkerDay
        fields = (
            'worker_id',
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

        if (attrs.get('worker_id') is None) and ('worker_username' in attrs):
            username = attrs.pop('worker_username')
            users = list(User.objects.filter(username=username, network_id=self.context['request'].user.network_id))
            if len(users) == 1:
                attrs['worker_id'] = users[0].id
            else:
                raise NotFound(detail=f'Пользователь "{username}" не найден')

        return attrs


class BlockOrUnblockWorkerDayWrapperSerializer(serializers.Serializer):
    worker_days = BlockOrUnblockWorkerDaySerializer(many=True)
