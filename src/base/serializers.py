import json
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import EmailValidator
from django.db.models import Q
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers
from rest_framework.exceptions import ValidationError, PermissionDenied
from rest_framework.validators import UniqueValidator

from src.base.fields import CurrentUserNetwork, UserworkShop
from src.base.message import Message
from src.base.models import (
    Employment,
    Network,
    NetworkConnect,
    User,
    FunctionGroup,
    WorkerPosition,
    Notification,
    Subscribe,
    Event,
    ShopSettings,
    Shop,
    Group,
    Break,
    ShopSchedule,
    Employee,
)
from src.timetable.serializers import EmploymentWorkTypeSerializer, EmploymentWorkTypeListSerializer
from src.timetable.worker_constraint.serializers import WorkerConstraintSerializer, WorkerConstraintListSerializer


class BaseNetworkSerializer(serializers.ModelSerializer):
    network_id = serializers.HiddenField(default=CurrentUserNetwork())


class OutsourceClientNetworkSerializer(serializers.Serializer):
    name = serializers.CharField()
    code = serializers.CharField()
    id = serializers.IntegerField()


class NetworkSerializer(serializers.ModelSerializer):
    logo = serializers.SerializerMethodField('get_logo_url')
    default_stats = serializers.SerializerMethodField()
    show_tabel_graph = serializers.SerializerMethodField()
    unaccounted_overtime_threshold = serializers.SerializerMethodField()
    show_remaking_choice = serializers.SerializerMethodField()

    def get_default_stats(self, obj: Network):
        default_stats = json.loads(obj.settings_values).get('default_stats', {})
        return {
            'timesheet_employee_top': default_stats.get('timesheet_employee_top', 'fact_total_all_hours_sum'),
            'timesheet_employee_bottom': default_stats.get('timesheet_employee_bottom', 'sawh_hours'),
            'employee_top': default_stats.get('employee_top', 'work_hours_total'),
            'employee_bottom': default_stats.get('employee_bottom', 'norm_hours_curr_month'),
            'day_top': default_stats.get('day_top', 'covering'),
            'day_bottom': default_stats.get('day_bottom', 'deadtime'),
        }

    def get_show_tabel_graph(self, obj:Network):
        return obj.settings_values_prop.get('show_tabel_graph', True)

    def get_unaccounted_overtime_threshold(self, obj:Network):
        return obj.settings_values_prop.get('unaccounted_overtime_threshold', 60)

    def get_show_remaking_choice(self, obj: Network):
        return obj.settings_values_prop.get('show_remaking_choice', False)

    def get_logo_url(self, obj) -> str:
        if obj.logo:
            return obj.logo.url
        return None

    class Meta:
        model = Network
        fields = [
            'id',
            'name',
            'logo',
            'url',
            'primary_color',
            'secondary_color',
            'allowed_geo_distance_km',
            'enable_camera_ticks',
            'show_worker_day_additional_info',
            'allowed_interval_for_late_arrival',
            'allowed_interval_for_early_departure',
            'default_stats',
            'show_tabel_graph',
            'show_worker_day_tasks',
            'show_user_biometrics_block',
            'unaccounted_overtime_threshold',
            'forbid_edit_employments_came_through_integration',
            'show_remaking_choice',
            'display_employee_tabs_in_the_schedule',
            'allow_creation_several_wdays_for_one_employee_for_one_date',
        ]

class NetworkListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    name = serializers.CharField()

class NetworkWithOutsourcingsAndClientsSerializer(NetworkSerializer):
    outsourcings = OutsourceClientNetworkSerializer(many=True)
    clients = OutsourceClientNetworkSerializer(many=True)

    class Meta(NetworkSerializer.Meta):
        fields = NetworkSerializer.Meta.fields + ['outsourcings', 'clients']


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
    username = serializers.CharField()
    network_id = serializers.IntegerField()
    has_biometrics = serializers.SerializerMethodField()

    def get_avatar_url(self, obj) -> str:
        if obj.avatar:
            return obj.avatar.url
        return None

    def get_has_biometrics(self, obj) -> bool:
        if getattr(obj, 'userconnecter_id', None):
            return True
        else:
            return False


class UserShorSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()
    middle_name = serializers.CharField()
    avatar = serializers.SerializerMethodField('get_avatar_url')

    def get_avatar_url(self, obj) -> str:
        if obj.avatar:
            return obj.avatar.url
        return None


class UserSerializer(BaseNetworkSerializer):
    username = serializers.CharField(required=False, validators=[UniqueValidator(queryset=User.objects.all())])
    network_id = serializers.HiddenField(default=CurrentUserNetwork())
    avatar = serializers.SerializerMethodField('get_avatar_url')
    email = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = User
        fields = ['id', 'first_name', 'last_name', 'middle_name', 'network_id',
                  'birthday', 'sex', 'avatar', 'email', 'phone_number', 'username', 'auth_type', 'ldap_login']

    def validate(self, attrs):
        email = attrs.get('email')
        if email:
            try:
                EmailValidator()(email)
            except DjangoValidationError:
                # TODO: добавить запись в лог?
                attrs['email'] = ''

        auth_type = attrs.get('auth_type')
        if auth_type == User.LDAP_AUTH and not attrs.get('ldap_login'):
            raise serializers.ValidationError('ldap_login should be specified for ldap auth_type.')

        return attrs

    def get_avatar_url(self, obj) -> str:
        if obj.avatar:
            return obj.avatar.url
        return None


class EmployeeSerializer(BaseNetworkSerializer):
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(required=False, write_only=True)
    has_shop_employment = serializers.BooleanField(required=False, read_only=True)

    class Meta:
        model = Employee
        fields = ['id', 'user', 'user_id', 'tabel_code', 'has_shop_employment']
        extra_kwargs = {
            'tabel_code': {
                'required': False,
            },
        }

    def __init__(self, *args, **kwargs):
        super(EmployeeSerializer, self).__init__(*args, **kwargs)
        request = self.context.get('request')
        if request and request.query_params.get('include_employments'):
            self.fields['employments'] = EmploymentSerializer(
                required=False, many=True, read_only=True, context=self.context, source='employments_list')


class AuthUserSerializer(UserSerializer):
    network = NetworkWithOutsourcingsAndClientsSerializer()
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


class AutoTimetableSerializer(serializers.Serializer):
    auto_timetable = serializers.BooleanField()
    employment_ids = serializers.ListField(child=serializers.IntegerField())


class EmploymentListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    employee_id = serializers.IntegerField(required=False)
    user_id = serializers.IntegerField(source='employee.user_id')
    shop_id = serializers.IntegerField(required=False)
    position_id = serializers.IntegerField()
    is_fixed_hours = serializers.BooleanField()
    dt_hired = serializers.DateField()
    dt_fired = serializers.DateField()
    salary = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    week_availability = serializers.IntegerField()
    norm_work_hours = serializers.FloatField()
    min_time_btw_shifts = serializers.IntegerField()
    shift_hours_length_min = serializers.IntegerField()
    shift_hours_length_max = serializers.IntegerField()
    auto_timetable = serializers.BooleanField(default=True)
    tabel_code = serializers.CharField(source='employee.tabel_code')
    is_ready_for_overworkings = serializers.BooleanField()
    dt_new_week_availability_from = serializers.DateField()
    is_visible = serializers.BooleanField()
    worker_constraints = WorkerConstraintListSerializer(many=True)
    work_types = EmploymentWorkTypeListSerializer(many=True)

    def __init__(self, *args, **kwargs):
        super(EmploymentListSerializer, self).__init__(*args, **kwargs)

        request = self.context.get('request')
        if request and request.query_params.get('include_employee'):
            self.fields['employee'] = EmployeeSerializer(required=False, read_only=True)


class EmploymentSerializer(serializers.ModelSerializer):
    default_error_messages = {
        "emp_check_dates": _("Employment from {dt_hired} to {dt_fired} already exists."),
        "no_user_with_username": _("There is {amount} models of user with username: {username}."),
        "no_user_with_user_id": _("There is {amount} models of user with user_id: {user_id}."),
        "no_shop": _("There is {amount} models of shop with code: {code}."),
        "no_position": _("There is {amount} models of position with code: {code}."),
        "no_network_connect": _("You are not allowed to choose shops from other network."),
        "bad_network_shop_position": _("Network of shop and position should be equal.")
    }

    position_id = serializers.IntegerField(required=False)
    position_code = serializers.CharField(required=False, source='position.code')
    shop_id = serializers.IntegerField(required=False)
    shop_code = serializers.CharField(required=False, source='shop.code')
    user_id = serializers.IntegerField(required=False, source='employee.user_id')
    employee_id = serializers.IntegerField(required=False)
    function_group_id = serializers.IntegerField(required=False, allow_null=True)
    work_types = EmploymentWorkTypeSerializer(many=True, read_only=True, source='work_types_list')
    worker_constraints = WorkerConstraintSerializer(many=True, source='worker_constraints_list')
    username = serializers.CharField(required=False, source='employee.user.username')
    dt_hired = serializers.DateField(required=True)
    dt_fired = serializers.DateField(required=False, default=None)
    tabel_code = serializers.CharField(required=False, source='employee.tabel_code')
    is_active = serializers.BooleanField(read_only=True)

    class Meta:
        model = Employment
        fields = ['id', 'user_id', 'shop_id', 'position_id', 'is_fixed_hours', 'dt_hired', 'dt_fired',
                  'salary', 'week_availability', 'norm_work_hours', 'min_time_btw_shifts',
                  'shift_hours_length_min', 'shift_hours_length_max', 'auto_timetable', 'tabel_code', 'is_ready_for_overworkings',
                  'dt_new_week_availability_from', 'is_visible',  'worker_constraints', 'work_types',
                  'shop_code', 'position_code', 'username', 'code', 'function_group_id', 'dt_to_function_group',
                  'employee_id', 'is_active',
        ]
        create_only_fields = ['employee_id']
        read_only_fields = []
        extra_kwargs = {
            'auto_timetable': {
                'default': True,
            },
            'is_visible': {
                'default': True,
            },
        }
        timetable_fields = [
            'function_group_id', 'is_fixed_hours', 'salary', 'week_availability', 'norm_work_hours', 'shift_hours_length_min', 
            'shift_hours_length_max', 'min_time_btw_shifts', 'is_ready_for_overworkings', 'is_visible',
        ]

    def validate(self, attrs):
        employee = attrs.pop('employee', {})
        if self.instance:
            # Нельзя обновить пользователя по коду
            attrs['employee_id'] = self.instance.employee_id  # TODO: правильно?
        else:
            if not attrs.get('employee_id'):
                user = employee.pop('user', None)
                tabel_code = employee.pop('tabel_code', None)
                user_id = employee.pop('user_id', None)
                user_kwargs = {}
                if user:
                    user_kwargs['username'] = user['username']
                if user_id:
                    user_kwargs['id'] = user_id

                users = list(User.objects.filter(
                    network_id=self.context['request'].user.network_id, **user_kwargs,
                ))
                if len(users) == 1:
                    employee, _employee_created = Employee.objects.get_or_create(
                        user=users[0],
                        tabel_code=tabel_code,
                    )
                    attrs['employee_id'] = employee.id
                else:
                    if user:
                        self.fail('no_user_with_username', amount=len(users), username=user['username'])
                    self.fail('no_user_with_user_id', amount=len(users), user_id=user_id)

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
        if attrs.get('shop_id'):
            shop = Shop.objects.get(id=attrs['shop_id'])
            connector = NetworkConnect.objects.filter(
                outsourcing_id=self.context['request'].user.network_id,
                client_id=shop.network_id,
                allow_choose_shop_from_client_for_employement=True,
            )
            if not (shop.network_id == self.context['request'].user.network_id) and not connector.exists():
                raise serializers.ValidationError(self.error_messages['no_network_connect'])
        elif self.instance:
            shop = self.instance.shop
        else:
            raise ValidationError({'shop_id': self.error_messages['required']})
        
        if attrs.get('position_id'):
            position = WorkerPosition.objects.get(id=attrs['position_id'])
            if shop.network_id != position.network_id:
                raise serializers.ValidationError(self.error_messages['bad_network_shop_position'])

        if self.context['request'].user.network.descrease_employment_dt_fired_in_api:
            if 'dt_hired' in attrs and attrs['dt_fired']:
                attrs['dt_fired'] = attrs['dt_fired'] - timedelta(1)

        return attrs

    def __init__(self, *args, **kwargs):
        super(EmploymentSerializer, self).__init__(*args, **kwargs)

        request = self.context.get('request')
        if request and request.query_params.get('include_employee'):
            self.fields['employee'] = EmployeeSerializer(required=False, read_only=True)

        show_constraints = None
        if self.context.get('request'):
            show_constraints = self.context['request'].query_params.get('show_constraints')

        if not show_constraints:
            self.fields.pop('worker_constraints')
        
        if self.context.get('view') and self.context['view'].action == 'timetable':
            exclude_fields = set(self.Meta.fields).difference(set(self.Meta.timetable_fields))
            for f in exclude_fields:
                self.fields.pop(f, None)

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
            if 'employee_id' not in data and 'employee' not in data:
                raise ValidationError({'employee_id': self.error_messages['required']})
            if 'position_id' not in data and 'position' not in data:
                raise ValidationError({'position_id': self.error_messages['required']})

        return data

    def update(self, instance, validated_data, *args, **kwargs):
        if instance.function_group_id != validated_data.get('function_group_id', instance.function_group_id):
            user = self.context['request'].user
            group_from = instance.function_group_id
            group_to = validated_data.get('function_group_id')
            group_from_perm = True
            if group_from:
                group_from_perm = Group.objects.filter(
                    Q(employments__employee__user=user) | Q(workerposition__employment__employee__user=user),
                    subordinates__id=group_from,
                ).exists()
            group_to_perm = True
            if group_to:
                group_to_perm = Group.objects.filter(
                    Q(employments__employee__user=user) | Q(workerposition__employment__employee__user=user),
                    subordinates__id=group_to,
                ).exists()
            has_perm = group_from_perm and group_to_perm
            if not has_perm:
                raise PermissionDenied()
        if instance.is_visible != validated_data.get('is_visible', True):
            Employment.objects.filter(
                shop_id=instance.shop_id, 
                employee_id=instance.employee_id,
            ).update(is_visible=validated_data.get('is_visible', True))

        if getattr(self.context['request'], 'by_code', False) and self.context[
            'request'].user.network.ignore_shop_code_when_updating_employment_via_api:
            validated_data.pop('shop_id', None)

        return super().update(instance, validated_data, *args, **kwargs)


class WorkerPositionSerializer(BaseNetworkSerializer):
    class Meta:
        model = WorkerPosition
        fields = ['id', 'name', 'network_id', 'code', 'breaks_id']

    def __init__(self, *args, **kwargs):
        super(WorkerPositionSerializer, self).__init__(*args, **kwargs)
        if not self.context.get('request'):
            return
        self.fields['code'].validators.append(
            UniqueValidator(
                WorkerPosition.objects.filter(network=self.context.get('request').user.network)
            )
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['network_id'] = instance.network_id # create/read-only field
        return data


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

    def get_message(self, instance) -> str:
        lang = self.context['request'].user.lang

        event = instance.event
        message = Message(lang=lang)
        if event.type == 'vacancy':
            details = event.worker_day
            params = {'details': details, 'dt': details.dt, 'shop': event.shop, 'domain': settings.EXTERNAL_HOST}
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
                  'breaks_id',
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


class BreakSerializer(BaseNetworkSerializer):
    class Meta:
        model = Break
        fields = ['id', 'name', 'network_id', 'value']
    
    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['value'] = instance.breaks
        return data


class ShopScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopSchedule
        fields = (
            'pk',
            'modified_by',
            'shop_id',
            'dt',
            'type',
            'opens',
            'closes',
        )
        extra_kwargs = {
            'modified_by': {
                'read_only': True,
            },
            'shop_id': {
                'read_only': True,
            },
            'dt': {
                'read_only': True,
            },
        }
