from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.validators import UniqueValidator

from django.conf import settings
from django.contrib.auth.forms import SetPasswordForm
from django.db.models import Q

from src.base.models import Employment, Network, User, FunctionGroup, WorkerPosition, Notification, Subscribe, Event, ShopSettings, Shop, Group
from src.base.message import Message
from src.base.fields import CurrentUserNetwork, UserworkShop
from src.timetable.serializers import EmploymentWorkTypeSerializer, WorkerConstraintSerializer, WorkerConstraintListSerializer, EmploymentWorkTypeListSerializer


class BaseNetworkSerializer(serializers.ModelSerializer):
    network_id = serializers.HiddenField(default=CurrentUserNetwork())


class NetworkSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField('get_logo_url')
    def get_logo_url(self, obj):
        if obj.logo:
            return obj.logo.url
        return None
    class Meta:
        model = Network
        fields = ['id', 'name', 'logo', 'url', 'primary_color', 'secondary_color']


class UserListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    middle_name = serializers.CharField()
    birthday = serializers.DateField()
    sex = serializers.CharField()
    avatar = serializers.SerializerMethodField('get_avatar_url')
    email = serializers.CharField()
    phone_number = serializers.CharField()
    tabel_code = serializers.CharField()
    username = serializers.CharField()
    network_id = serializers.IntegerField()

    def get_avatar_url(self, obj):
        if obj.avatar:
            return obj.avatar.url
        return None

class UserSerializer(BaseNetworkSerializer):
    username = serializers.CharField(required=False, validators=[UniqueValidator(queryset=User.objects.all())])
    network_id = serializers.HiddenField(default=CurrentUserNetwork())
    avatar = serializers.SerializerMethodField('get_avatar_url')

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'middle_name', 'network_id',
                  'birthday', 'sex', 'avatar', 'email', 'phone_number', 'tabel_code', 'username' ]
    def get_avatar_url(self, obj):
        if obj.avatar:
            return obj.avatar.url
        return None


class AuthUserSerializer(UserSerializer):
    network = NetworkSerializer()
    shop_id = serializers.CharField(default=UserworkShop())

    class Meta(UserSerializer.Meta):
        fields = UserSerializer.Meta.fields + ['network', 'shop_id']


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


class EmploymentListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    user_id = serializers.IntegerField(required=False)
    shop_id = serializers.IntegerField(required=False)
    position_id = serializers.IntegerField()
    is_fixed_hours = serializers.BooleanField()
    dt_hired = serializers.DateField()
    dt_fired = serializers.DateField()
    salary = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    week_availability = serializers.IntegerField()
    norm_work_hours = serializers.IntegerField()
    min_time_btw_shifts = serializers.IntegerField()
    shift_hours_length_min = serializers.IntegerField()
    shift_hours_length_max = serializers.IntegerField()
    auto_timetable = serializers.BooleanField()
    tabel_code = serializers.CharField()
    is_ready_for_overworkings = serializers.BooleanField()
    dt_new_week_availability_from = serializers.DateField()
    user = UserListSerializer()
    is_visible = serializers.BooleanField()
    worker_constraints = WorkerConstraintListSerializer(many=True)
    work_types = EmploymentWorkTypeListSerializer(many=True)


class EmploymentSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "emp_check_dates": _("Employment from {dt_hired} to {dt_fired} already exists."),
        "no_user": _("There is {amount} models of user with username: {username}."),
        "no_shop": _("There is {amount} models of shop with code: {code}."),
        "no_position": _("There is {amount} models of position with code: {code}."),
    }

    user = UserSerializer(read_only=True)
    position_id = serializers.IntegerField(required=False)
    position_code = serializers.CharField(required=False, source='position.code')
    shop_id = serializers.IntegerField(required=False)
    shop_code = serializers.CharField(required=False, source='shop.code')
    user_id = serializers.IntegerField(required=False)
    work_types = EmploymentWorkTypeSerializer(many=True, read_only=True)
    worker_constraints = WorkerConstraintSerializer(many=True)
    username = serializers.CharField(required=False, source='user.username')
    dt_hired = serializers.DateField(required=True)
    dt_fired = serializers.DateField(required=False, default=None)

    class Meta:
        model = Employment
        fields = ['id', 'user_id', 'shop_id', 'position_id', 'is_fixed_hours', 'dt_hired', 'dt_fired',
                  'salary', 'week_availability', 'norm_work_hours', 'min_time_btw_shifts',
                  'shift_hours_length_min', 'shift_hours_length_max', 'auto_timetable', 'tabel_code', 'is_ready_for_overworkings',
                  'dt_new_week_availability_from', 'user', 'is_visible',  'worker_constraints', 'work_types',
                  'shop_code', 'position_code', 'username'
        ]
        create_only_fields = ['user_id', 'shop_id', 'shop', 'tabel_code', 'user']
        read_only_fields = ['user']

    def validate(self, attrs):
        if self.instance:
            # Нельзя обновить пользователя по коду
            attrs['user_id'] = self.instance.user_id
            # shop_id = self.instance.user_id
        else:

            if not attrs.get('user_id'):
                user = attrs.pop('user')
                users = list(User.objects.filter(username=user['username'], network_id=self.context['request'].user.network_id))
                if len(users) == 1:
                    attrs['user_id'] = users[0].id
                else:
                    self.fail('no_user', amount=len(users), username=user['username'])
            #
            # if not attrs.get('shop_id'):
            #     shop = attrs.pop('shop')
            #     shops = list(Shop.objects.filter(code=shop['code'], network_id=self.context['request'].user.network_id))
            #     if len(shops) == 1:
            #         attrs['shop_id'] = shops[0].id
            #     else:
            #         self.fail('no_shop', amount=len(shops), code=shop['code'])
            #
            # user_id = attrs['user_id']
            # shop_id = attrs['shop_id']

        if (attrs.get('shop_id') is None) and ('code' in attrs.get('position', {})):
            position = attrs.pop('position', None)
            positions = list(WorkerPosition.objects.filter(code=position['code'], network_id=self.context['request'].user.network_id))
            if len(positions) == 1:
                attrs['position_id'] = positions[0].id
            else:
                self.fail('no_position', amount=len(positions), code=position['code'])

        if (attrs.get('shop_id') is None) and ('code' in attrs.get('shop', {})):
            shop = attrs.pop('shop')
            shops = list(Shop.objects.filter(code=shop['code'], network_id=self.context['request'].user.network_id))
            if len(shops) == 1:
                attrs['shop_id'] = shops[0].id
            else:
                self.fail('no_shop', amount=len(shops), code=shop['code'])

        # employments = Employment.objects.filter(
        #     Q(dt_fired__isnull=True) | Q(dt_fired__gte=attrs.get('dt_hired')),
        #     user_id=user_id,
        #     shop_id=shop_id,
        # )
        # if attrs.get('dt_fired'):
        #     employments=employments.filter(dt_hired__lte=attrs['dt_fired'])
        # if self.instance:
        #     employments = employments.exclude(id=self.instance.id)
        # if employments:
        #     e = employments.first()
        #     self.fail('emp_check_dates',dt_hired=e.dt_hired,dt_fired=e.dt_fired)
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
            if 'shop_id' not in data and 'shop' not in data and 'code' not in data['shop']:
                raise ValidationError({'shop_id': self.error_messages['required']})
            if 'user_id' not in data and 'user' not in data:
                raise ValidationError({'user_id': self.error_messages['required']})
            if 'position_id' not in data and 'position' not in data:
                raise ValidationError({'position_id': self.error_messages['required']})

        return data


class WorkerPositionSerializer(BaseNetworkSerializer):
    class Meta:
        model = WorkerPosition
        fields = ['id', 'name', 'network_id', 'code', 'default_work_type_names']


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
    network_id = serializers.IntegerField(default=CurrentUserNetwork(), write_only=True)

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
                  'max_work_hours_7days',
                  'network_id',
                  ]


class SubscribeSerializer(serializers.ModelSerializer):
    shop_id = serializers.IntegerField(required=True)

    class Meta:
        model = Subscribe
        fields = ['id','shop_id', 'type']


class GroupSerializer(serializers.ModelSerializer):
    network_id = serializers.HiddenField(default=CurrentUserNetwork())
    class Meta:
        model = Group
        fields = ['id', 'name', 'code', 'network_id']
