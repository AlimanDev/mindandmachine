from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueValidator

from django.conf import settings
from django.contrib.auth.forms import SetPasswordForm
from django.db.models import Q

from src.base.models import Employment, Network, User, FunctionGroup, WorkerPosition, Notification, Subscribe, Event, ShopSettings
from src.base.message import Message
from src.base.fields import CurrentUserNetwork
from src.timetable.serializers import EmploymentWorkTypeSerializer, WorkerConstraintSerializer


class BaseNetworkSerializer(serializers.ModelSerializer):
    network_id = serializers.HiddenField(default=CurrentUserNetwork())


class NetworkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Network
        fields = ['id', 'name', 'logo', 'url', 'primary_color', 'secondary_color']


class UserSerializer(BaseNetworkSerializer):
    username = serializers.CharField(required=False, validators=[UniqueValidator(queryset=User.objects.all())])

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'middle_name',
                  'birthday', 'sex', 'avatar', 'email', 'phone_number', 'tabel_code', 'username' ]


class AuthUserSerializer(UserSerializer):
    network = NetworkSerializer()

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['network']

class PasswordSerializer(serializers.Serializer):
    default_error_messages = {
        "password_mismatch": _("Passwords are mismatched."),
        "password_wrong": _("Password is wrong."),
    }
    confirmation_password = serializers.CharField(required=True, max_length=30)
    new_password1 = serializers.CharField(required=True, max_length=30)
    new_password2 = serializers.CharField(required=True, max_length=30)

    def validate(self, data):
        if not self.context['request'].user.check_password(data.get('confirmation_password')):
            self.fail('password_wrong')

        if data.get('new_password1') != data.get('new_password2'):
            self.fail('password_mismatch')
        form = SetPasswordForm(user=self.instance, data=data )
        if not form.is_valid():
            raise ValidationError(form.errors)

        return data

    def update(self, instance, validated_data):
        instance.set_password(validated_data['new_password1'])
        instance.save()
        return instance

    def create(self, validated_data):
        pass


class FunctionGroupSerializer(serializers.ModelSerializer):
    class Meta:
        model = FunctionGroup
        fields = ['id', 'group_id', 'func', 'method']


class EmploymentSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "emp_check_dates": _("Employment from {dt_hired} to {dt_fired} already exists."),
    }
    user = UserSerializer(read_only=True)
    position_id = serializers.IntegerField()
    shop_id = serializers.IntegerField(required=False)
    shop_code = serializers.CharField(required=False)
    user_id = serializers.IntegerField(required=False)
    user_code = serializers.CharField(required=False)
    work_types = EmploymentWorkTypeSerializer(many=True, read_only=True)
    worker_constraints = WorkerConstraintSerializer(many=True)

    class Meta:
        model = Employment
        fields = ['id', 'user_id', 'shop_id', 'position_id', 'is_fixed_hours', 'dt_hired', 'dt_fired',
                  'salary', 'week_availability', 'norm_work_hours', 'min_time_btw_shifts',
                  'shift_hours_length_min', 'shift_hours_length_max', 'auto_timetable', 'tabel_code', 'is_ready_for_overworkings',
                  'dt_new_week_availability_from', 'user', 'is_visible',  'worker_constraints', 'work_types',
                  'shop_code', 'user_code',
        ]
        create_only_fields = ['user_id', 'shop_id']
        read_only_fields = ['user']

    def validate(self, attrs):
        if self.instance:
            user_id = self.instance.user_id
            shop_id = self.instance.shop_id
        else:
            user_id = attrs['user_id']
            shop_id = attrs['shop_id']
        employments = Employment.objects.filter(
            Q(dt_fired__isnull=True)|Q(dt_fired__gte=attrs['dt_hired']),
            user_id=user_id,
            shop_id=shop_id,
        )
        if attrs.get('dt_fired'):
            employments=employments.filter( dt_hired__lte=attrs['dt_fired'])
        if self.instance:
            employments = employments.exclude(id=self.instance.id)
        if employments:
            e=employments.first()
            self.fail('emp_check_dates',dt_hired=e.dt_hired,dt_fired=e.dt_fired)
        return attrs

    def __init__(self, *args, **kwargs):
        super(EmploymentSerializer, self).__init__(*args, **kwargs)

        show_constraints = None
        if self.context['request']:
            show_constraints = self.context['request'].query_params.get('show_constraints')

        if not show_constraints:
            self.fields.pop('worker_constraints')

    def to_internal_value(self, data):
        data = super(EmploymentSerializer, self).to_internal_value(data)
        if self.instance:
            # update
            for field in self.Meta.create_only_fields:
                if field in data:
                    data.pop(field)
        else:
            # shop_id is required for create
            for field in self.Meta.create_only_fields:
                if field not in data:
                    raise ValidationError({field: self.error_messages['required']})
        return data


class WorkerPositionSerializer(BaseNetworkSerializer):
    class Meta:
        model = WorkerPosition
        fields = ['id', 'name', 'network_id']


class EventSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField()

    class Meta:
        model = Event
        fields = ['type', 'shop_id']


class NotificationSerializer(serializers.ModelSerializer):
    event = EventSerializer(read_only=True)
    message = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = ['id','worker_id', 'is_read', 'event', 'message']
        read_only_fields = ['worker_id', 'event']

    def get_message(self, instance):
        lang = self.context['request'].user.lang

        event = instance.event
        message = Message(lang=lang)
        if event.type == 'vacancy':
            details = event.worker_day
            params = {'details': details, 'dt': details.dt, 'shop': event.shop, 'domain': settings.DOMAIN}
        else:
            params = event.params
        return message.get_message(event.type, params)


class ShopSettingsSerializer(serializers.ModelSerializer):

    class Meta:
        model = ShopSettings
        fields = ['id', 'name', 'fot', 'idle', 'less_norm',
                  'shift_start',
                  'shift_end',
                  'min_change_time',
                  'even_shift_morning_evening',
                  'paired_weekday',
                  'exit1day',
                  'exit42hours',
                  'process_type',
                  'absenteeism',
                  'queue_length',
                  'max_work_hours_7days'
                  ]


class SubscribeSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(required=True)

    class Meta:
        model = Subscribe
        fields = ['id','shop_id', 'type']

