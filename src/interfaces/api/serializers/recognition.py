from datetime import timedelta
import geopy.distance
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from rest_framework import serializers

from src.apps.base.models import Shop, NetworkConnect, Employee
from src.interfaces.api.serializers.base import BaseModelSerializer
from src.apps.recognition.models import TickPoint, Tick, TickPhoto, ShopIpAddress
from src.apps.timetable.models import User as WFMUser
from src.common.drf.fields import RoundingDecimalField
from src.common.utils import generate_user_token


class HashSigninSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    token = serializers.CharField(max_length=128)

    def get_token(self, login):
        return generate_user_token(login)

    def validate(self, attrs):
        username = attrs.get('username', '')
        if settings.CASE_INSENSITIVE_AUTH:
            username = username.lower()
        token = attrs.get('token')

        if username and token:
            user = None
            if token == self.get_token(username):
                lookup_str = 'username'
                if settings.CASE_INSENSITIVE_AUTH:
                    lookup_str = 'username__iexact'
                user = WFMUser.objects.filter(**{lookup_str: username}).first()

            if not user:
                msg = _('Unable to log in with provided credentials.')
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = _('Must include "username" and "password".')
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs


class TickPointSerializer(BaseModelSerializer):
    shop_id = serializers.IntegerField()

    class Meta:
        model = TickPoint
        fields = ['id', 'shop_id', 'name', 'code', 'key']
        extra_kwargs = {
            'key': {
                'read_only': True,
            },
        }


class TickSerializer(BaseModelSerializer):
    lateness = serializers.SerializerMethodField()
    # worker_day_details = serializers.SerializerMethodField()
    # worker_day_details = WorkerDayDetailsSerializer(many=True)
    is_verified = serializers.SerializerMethodField()

    class Meta:
        model = Tick
        read_only_fields = [
            'id',
            'dttm',
            'lateness',
            'is_verified',
            'type',
            'user_id',
            'employee_id',
            'tick_point_id',
        ]
        fields = read_only_fields

    def get_is_verified(self, obj) -> int:
        return 1 if obj.verified_score else 0

    # def get_worker_day_details(self, obj):
    #     if obj.worker_day:
    #         return WorkerDayDetailsSerializer(obj.worker_day.worker_day_details, many=True).data
    #     return []

    def get_lateness(self, obj) -> int:
        return int(obj.lateness.total_seconds()) if isinstance(obj.lateness, timedelta) else None


class PostTickSerializer_point(BaseModelSerializer):
    user_id = serializers.IntegerField()
    employee_id = serializers.IntegerField(required=False)
    dttm = serializers.DateTimeField(required=False)

    def validate(self, attrs):
        if attrs['employee_id'] is None and attrs['user_id']:
            employee = Employee.objects.filter(user_id=attrs['user_id']).order_by('-id').first()
            if employee:
                attrs['employee_id'] = employee.id

    class Meta:
        model = Tick
        fields = ['user_id', 'employee_id', 'type', 'dttm']


class PostTickSerializer_user(BaseModelSerializer):
    dttm = serializers.DateTimeField(required=False)
    employee_id = serializers.IntegerField(required=False)

    class Meta:
        model = Tick
        fields = ['type', 'dttm', 'employee_id']

    def __init__(self, *args, **kwargs):
        super(PostTickSerializer_user, self).__init__(*args, **kwargs)
        clients = NetworkConnect.objects.filter(outsourcing=self.context['request'].user.network).values_list('client_id', flat=True)
        self.fields['shop_code'] = serializers.SlugRelatedField(
            slug_field='code', queryset=Shop.objects.filter(Q(network=self.context['request'].user.network) | Q(network_id__in=clients)))
        if self.context['request'].user.network.allowed_geo_distance_km:
            self.fields['lat'] = RoundingDecimalField(decimal_places=8, max_digits=12)
            self.fields['lon'] = RoundingDecimalField(decimal_places=8, max_digits=12)

    def validate(self, attrs):
        if self.context['request'].user.network.allowed_geo_distance_km:
            if not attrs['shop_code'].latitude or not attrs['shop_code'].longitude:
                raise serializers.ValidationError(
                    'Для выбранного магазина не настроены координаты. Пожалуйста, обратитесь к администратору системы.')
            distance = geopy.distance.distance(
                (attrs['lat'], attrs['lon']),
                (attrs['shop_code'].latitude, attrs['shop_code'].longitude),
            )
            if distance.km > self.context['request'].user.network.allowed_geo_distance_km:
                raise serializers.ValidationError(
                    (_("The distance to the department should not exceed {allowed_distance_km} km "
                       "({distance_now_km} km now)")).format(
                        allowed_distance_km=self.context['request'].user.network.allowed_geo_distance_km,
                        distance_now_km=round(distance.km, 2),
                    )
                )

        return attrs


class TickPhotoSerializer(BaseModelSerializer):
    is_verified = serializers.SerializerMethodField()

    class Meta:
        model = TickPhoto
        read_only_fields = [
            'id',
            'dttm',
            'verified_score',
            'type',
            'liveness',
            'is_verified',
        ]
        fields = read_only_fields + ['tick_id', 'image']

    def get_is_verified(self, obj):
        return 1 if obj.verified_score else 0


class PostTickPhotoSerializer(BaseModelSerializer):
    tick_id = serializers.IntegerField()
    dttm = serializers.DateTimeField(required=False)

    class Meta:
        model = TickPhoto
        fields = ['tick_id', 'type', 'image', 'dttm']


class DownloadTickPhotoExcelSerializer(serializers.Serializer):
    dt_from = serializers.DateField(required=False)
    dt_to = serializers.DateField(required=False)


class ShopIpAddressSerializer(BaseModelSerializer):

    class Meta:
        model = ShopIpAddress
        fields = ['id', 'ip_address', 'shop']
