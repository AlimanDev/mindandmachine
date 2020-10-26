from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from src.base.models import Employment, User, Shop
from src.base.shop.serializers import ShopSerializer
from src.conf.djconfig import QOS_DATE_FORMAT
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, EmploymentWorkType, WorkerConstraint
from src.util.models_converter import Converter


class WorkerDayApproveSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField(required=True)
    is_fact = serializers.BooleanField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()


class WorkerDayCashboxDetailsSerializer(serializers.ModelSerializer):
    work_type_id = serializers.IntegerField(required=False)

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
    comment = serializers.CharField()
    is_approved = serializers.BooleanField()
    worker_day_details = WorkerDayCashboxDetailsListSerializer(many=True)
    is_fact = serializers.BooleanField()
    work_hours = serializers.SerializerMethodField()
    parent_worker_day_id = serializers.IntegerField()
    shop_code = serializers.CharField(required=False, read_only=True)
    user_login = serializers.CharField(required=False, read_only=True)

    def __init__(self, *args, **kwargs):
        super(WorkerDayListSerializer, self).__init__(*args, **kwargs)
        if self.context.get('request').query_params.get('is_tabel'):
            self.fields['dttm_work_start'].source = 'tabel_dttm_work_start'
            self.fields['dttm_work_start'].source_attrs = ['tabel_dttm_work_start']
            self.fields['dttm_work_end'].source = 'tabel_dttm_work_end'
            self.fields['dttm_work_end'].source_attrs = ['tabel_dttm_work_end']

    def get_work_hours(self, obj):
        if self.context.get('request').query_params.get('is_tabel'):
            return getattr(obj, 'tabel_work_hours', obj.work_hours)

        return obj.work_hours


class WorkerDaySerializer(serializers.ModelSerializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
        'worker_day_exist': _("Worker day already exist."),
        'worker_day_intercept': _("Worker day intercepts with another: {shop_name}, {work_start}, {work_end}."),
        "no_user": _("There is {amount} models of user with username: {username}."),
        "no_shop": _("There is {amount} models of shop with code: {code}."),
    }

    worker_day_details = WorkerDayCashboxDetailsSerializer(many=True, required=False)
    worker_id = serializers.IntegerField(required=False, allow_null=True)
    employment_id = serializers.IntegerField(required=False, allow_null=True)
    shop_id = serializers.IntegerField(required=False)
    parent_worker_day_id = serializers.IntegerField(required=False, read_only=True)
    is_fact = serializers.BooleanField(required=False)
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    type = serializers.CharField(required=True)
    shop_code = serializers.CharField(required=False)
    user_login = serializers.CharField(required=False, read_only=True)
    username = serializers.CharField(required=False, write_only=True)
    created_by = serializers.HiddenField(default=serializers.CurrentUserDefault())

    class Meta:
        model = WorkerDay
        fields = ['id', 'worker_id', 'shop_id', 'employment_id', 'type', 'dt', 'dttm_work_start', 'dttm_work_end',
                  'comment', 'is_approved', 'worker_day_details', 'is_fact', 'work_hours', 'parent_worker_day_id',
                  'is_outsource', 'is_vacancy', 'shop_code', 'user_login', 'username', 'created_by']
        read_only_fields = ['work_hours', 'parent_worker_day_id']
        create_only_fields = ['is_fact']

    def validate(self, attrs):
        if self.instance and self.instance.is_approved:
            raise ValidationError({"error": "Нельзя менять подтвержденную версию."})

        is_fact = attrs['is_fact'] if 'is_fact' in attrs else getattr(self.instance, 'is_fact', None)
        type = attrs['type']

        if is_fact and type not in (WorkerDay.TYPE_WORKDAY, WorkerDay.TYPE_EMPTY):
            raise ValidationError({
                "error": "Для фактической неподтвержденной версии можно установить только 'Рабочий день' и 'НД'."
            })

        if not WorkerDay.is_type_with_tm_range(type):
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

        if not type == WorkerDay.TYPE_WORKDAY or is_fact:
            attrs.pop('worker_day_details', None)
        elif not (attrs.get('worker_day_details')):
            raise ValidationError({
                "worker_day_details": self.error_messages['required']
            })

        return attrs

    def create(self, validated_data):
        # self.check_other_worker_days(None, validated_data)
        is_fact = validated_data.get('is_fact')
        is_approved = validated_data.get('is_approved')

        # Если создаем факт то делаем его потомком подтвержденного факта или плана.
        # Если создаем план - делаем родителем факта и потомком подтвержденного плана.
        worker_days = WorkerDay.objects.filter(
            worker_id=validated_data.get('worker_id'),
            dt=validated_data.get('dt'),
            shop_id=validated_data.get('shop_id'),
        )
        wd = {
            'plan': {'approved': None, 'not_approved': None},
            'fact': {'approved': None, 'not_approved': None},
        }

        for w in worker_days:
            plan_or_fact = 'fact' if w.is_fact else 'plan'
            approved = 'approved' if w.is_approved else 'not_approved'
            wd[plan_or_fact][approved] = w

        # plan_to_bind = wd['plan']['approved'] if wd['plan']['approved'] else wd['plan']['not_approved'] if is_fact else None
        # fact_to_bind = wd['fact']['approved'] if wd['fact']['approved'] else wd['fact']['not_approved'] if not is_fact else None

        # Привязываем факт к подтвержденному факту или любому плану, план к подтвержденному плану
        # if is_fact and fact_to_bind:
        #     validated_data['parent_worker_day_id'] = fact_to_bind.id
        # elif plan_to_bind:
        #     validated_data['parent_worker_day_id'] = plan_to_bind.id

        details = validated_data.pop('worker_day_details', None)
        delete_model = None
        if is_fact:
            if is_approved:
                validated_data['parent_worker_day'] = wd['plan']['approved'] or wd['plan']['not_approved']
                delete_model = wd['fact']['approved']
            else:
                validated_data['parent_worker_day'] = wd['fact']['approved'] or wd['plan']['approved'] or wd['plan'][
                    'not_approved']
                delete_model = wd['fact']['not_approved']
        else:
            # план
            if is_approved:
                delete_model = wd['plan']['approved']
            else:
                validated_data['parent_worker_day'] = wd['plan']['approved']
                delete_model = wd['plan']['not_approved']

        worker_day = WorkerDay.objects.create(**validated_data)
        if delete_model:
            WorkerDay.objects.filter(parent_worker_day_id=delete_model.id).update(parent_worker_day_id=worker_day.id)
            delete_model.delete()

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
            is_approved=False
        )

        parent_worker_day_id = None
        if worker_day:
            worker_days = worker_days.exclude(id=worker_day.id)
            parent_worker_day_id = worker_day.parent_worker_day_id

        if parent_worker_day_id:
            worker_days = worker_days.exclude(id=parent_worker_day_id)

        if validated_data.get('is_vacancy') and validated_data.get('worker_id') == None:
            worker_days = None

        if worker_days:
            raise ValidationError({'error': self.error_messages['worker_day_exist']})

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


class EmploymentWorkTypeListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    work_type_id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    period = serializers.IntegerField()
    bills_amount = serializers.IntegerField()
    priority = serializers.IntegerField()
    duration = serializers.FloatField()


class EmploymentWorkTypeSerializer(serializers.ModelSerializer):
    employment_id = serializers.IntegerField(required=False)
    work_type_id = serializers.IntegerField(required=False)

    class Meta:
        model = EmploymentWorkType
        fields = ['id', 'work_type_id', 'employment_id', 'period', 'bills_amount', 'priority', 'duration']


class WorkerConstraintSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = WorkerConstraint
        fields = ['id', 'employment_id', 'weekday', 'is_lite', 'tm']
        extra_kwargs = {
            'employment_id': {
                'read_only': True,
            }
        }


class WrappedWorkerConstraintSerializer(serializers.Serializer):
    data = WorkerConstraintSerializer(many=True, )

    def create(self, validated_data):
        validated_data = validated_data.get('data')
        employment_id = self.context.get('view').kwargs.get('employment_pk')
        employment = Employment.objects.get(id=employment_id)
        to_create = []
        ids = []

        constraints = WorkerConstraint.objects.filter(
            employment_id=employment_id,
        )
        constraint_mapping = {constraint.id: constraint for constraint in constraints}

        wc_serializer = WorkerConstraintSerializer()
        for item in validated_data:
            if item.get('id'):
                if not constraint_mapping.get(item['id']):
                    raise ValidationError({"error": f"object with id {item['id']} does not exist"})
                wc_serializer.update(constraint_mapping[item['id']], item)
                ids.append(item['id'])
            else:
                constraint = WorkerConstraint(
                    **item,
                    employment_id=employment_id,
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
        return {'data': WorkerConstraint.objects.filter(employment_id=employment_id)}


class WorkerConstraintListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    weekday = serializers.IntegerField()
    is_lite = serializers.BooleanField()
    tm = serializers.TimeField()


class VacancySerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    worker_id = serializers.IntegerField()
    worker_day_details = WorkerDayCashboxDetailsListSerializer(many=True, required=False)
    shop = ShopSerializer()
    is_fact = serializers.BooleanField()
    is_approved = serializers.BooleanField()
    dttm_work_start = serializers.DateTimeField(default=None)
    dttm_work_end = serializers.DateTimeField(default=None)
    type = serializers.CharField()
    is_outsource = serializers.BooleanField()
    avatar = serializers.SerializerMethodField('get_avatar_url')
    worker_shop = serializers.IntegerField(required=False, default=None)

    def get_avatar_url(self, obj):
        if obj.worker_id and obj.worker.avatar:
            return obj.worker.avatar.url
        return None


class AutoSettingsSerializer(serializers.Serializer):
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    is_remaking = serializers.BooleanField(default=False)
    use_not_approved = serializers.BooleanField(default=False)


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


class DeleteTimetableSerializer(serializers.Serializer):
    default_error_messages = {
        'check_dates': _('Date start should be less then date end'),
    }
    shop_id = serializers.IntegerField()
    dt_from = serializers.DateField(format=QOS_DATE_FORMAT)
    dt_to = serializers.DateField(format=QOS_DATE_FORMAT, required=False, default=None)
    users = serializers.ListField(child=serializers.IntegerField(), required=False, default=[])
    types = serializers.ListField(child=serializers.CharField(), required=False, default=[])
    delete_all = serializers.BooleanField(default=False)
    except_created_by = serializers.BooleanField(default=True)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        dt_from = self.validated_data.get('dt_from')
        dt_to = self.validated_data.get('dt_to')

        if not self.validated_data.get('delete_all') and not dt_to:
            raise ValidationError({'dt_to': self.error_messages['required']})

        if dt_to and dt_from > dt_to:
            self.fail('check_dates')


class ExchangeSerializer(serializers.Serializer):
    default_error_messages = {
        'not_exist': _("Invalid pk \"{pk_value}\" - object does not exist.")
    }

    worker1_id = serializers.IntegerField()
    worker2_id = serializers.IntegerField()
    dates = serializers.ListField(child=serializers.DateField(format=QOS_DATE_FORMAT))
    is_approved = serializers.BooleanField(default=False)

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)
        for key in ['worker1_id', 'worker2_id']:
            if not User.objects.filter(id=self.validated_data[key]).exists():
                raise ValidationError({key: self.error_messages['not_exist'].format(pk_value=self.validated_data[key])})


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
