from rest_framework import serializers

from src.base.models import Employment, User, FunctionGroup, WorkerPosition, Notification, Subscribe, Event
from src.timetable.serializers import EmploymentWorkTypeSerializer, WorkerConstraintSerializer
from django.contrib.auth.forms import SetPasswordForm
from rest_framework.validators import UniqueValidator
from rest_framework.exceptions import ValidationError
from django.db.models import Q

from django.conf import settings
from src.base.message import Message
from src.base.exceptions import MessageError
class UserSerializer(serializers.ModelSerializer):
    username = serializers.CharField(required=False, validators=[UniqueValidator(queryset=User.objects.all())])

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'middle_name',
                  'birthday', 'sex', 'avatar', 'email', 'phone_number', 'tabel_code', 'username' ]


class PasswordSerializer(serializers.Serializer):
    confirmation_password = serializers.CharField(required=True, max_length=30)
    new_password1 = serializers.CharField(required=True, max_length=30)
    new_password2 = serializers.CharField(required=True, max_length=30)

    def validate(self, data):
        if not self.context['request'].user.check_password(data.get('confirmation_password')):
            raise MessageError(code='password_wrong', lang=self.context['request'].user.lang)

        if data.get('new_password1') != data.get('new_password2'):
            raise MessageError(code='password_mismatch', lang=self.context['request'].user.lang)
        form = SetPasswordForm(user=self.instance, data=data )
        if not form.is_valid():
            raise serializers.ValidationError(form.errors)

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
        fields = [ 'id', 'group_id', 'func', 'method']


class EmploymentSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    position_id = serializers.IntegerField()
    shop_id = serializers.IntegerField(required=False)
    user_id = serializers.IntegerField(required=False)
    work_types = EmploymentWorkTypeSerializer(many=True, read_only=True)
    worker_constraints = WorkerConstraintSerializer(many=True)

    class Meta:
        model = Employment
        fields = ['id', 'user_id', 'shop_id', 'position_id', 'is_fixed_hours', 'dt_hired', 'dt_fired',
                  'salary', 'week_availability', 'norm_work_hours', 'min_time_btw_shifts',
                  'shift_hours_length_min', 'shift_hours_length_max', 'auto_timetable', 'tabel_code', 'is_ready_for_overworkings',
                  'dt_new_week_availability_from', 'user', 'is_visible',  'worker_constraints', 'work_types'
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
        if attrs['dt_fired']:
            employments=employments.filter( dt_hired__lte=attrs['dt_fired'])
        if self.instance:
            employments = employments.exclude(id=self.instance.id)
        if employments:
            raise MessageError(code='emp_check_dates', params={'employment': employments.first()}, lang=self.context['request'].user.lang)
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
                    raise serializers.ValidationError({field:"This field is required"})
        return data


class WorkerPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkerPosition
        fields = ['id', 'name',]


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
        if event.type=='vacancy':
            details = event.worker_day_details
            params = {'details': details, 'dt': details.dttm_from.date(), 'shop': event.shop, 'domain': settings.DOMAIN}
        else:
            params = event.params
        return message.get_message(event.type, params)

class SubscribeSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(required=True)

    class Meta:
        model = Subscribe
        fields = ['id','shop_id', 'type']
