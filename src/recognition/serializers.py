import geopy.distance
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers

from src.base.models import Shop
from src.recognition.models import TickPoint, Tick, TickPhoto
from src.timetable.models import User as WFMUser
from src.util.drf.fields import RoundingDecimalField
from src.util.utils import generate_user_token


class HashSigninSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    token = serializers.CharField(max_length=128)

    def get_token(self, login):
        return generate_user_token(login)

    def validate(self, attrs):
        username = attrs.get('username')
        token = attrs.get('token')

        if username and token:
            user = None
            if token == self.get_token(username):
                user = WFMUser.objects.filter(username=username).first()

            if not user:
                msg = _('Unable to log in with provided credentials.')
                raise serializers.ValidationError(msg, code='authorization')
        else:
            msg = _('Must include "username" and "password".')
            raise serializers.ValidationError(msg, code='authorization')

        attrs['user'] = user
        return attrs


class TickPointSerializer(serializers.ModelSerializer):
    class Meta:
        model = TickPoint
        fields = ['id', 'shop_id', 'title']


class TickSerializer(serializers.ModelSerializer):
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
            'tick_point_id',
        ]
        fields = read_only_fields

    def get_is_verified(self, obj):
        return 1 if obj.verified_score else 0

    # def get_worker_day_details(self, obj):
    #     if obj.worker_day:
    #         return WorkerDayDetailsSerializer(obj.worker_day.worker_day_details, many=True).data
    #     return []

    def get_lateness(self, obj):
        return int(obj.lateness.total_seconds())


class PostTickSerializer_point(serializers.ModelSerializer):
    user_id = serializers.IntegerField()
    dttm = serializers.DateTimeField(required=False)

    class Meta:
        model = Tick
        fields = ['user_id', 'type', 'dttm']


class PostTickSerializer_user(serializers.ModelSerializer):
    dttm = serializers.DateTimeField(required=False)

    class Meta:
        model = Tick
        fields = ['type', 'dttm']

    def __init__(self, *args, **kwargs):
        super(PostTickSerializer_user, self).__init__(*args, **kwargs)
        self.fields['shop_code'] = serializers.SlugRelatedField(
            slug_field='code', queryset=Shop.objects.filter(network=self.context['request'].user.network))
        if self.context['request'].user.network.allowed_geo_distance_km:
            self.fields['lat'] = RoundingDecimalField(decimal_places=6, max_digits=12)
            self.fields['lon'] = RoundingDecimalField(decimal_places=6, max_digits=12)

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


class TickPhotoSerializer(serializers.ModelSerializer):
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


class PostTickPhotoSerializer(serializers.ModelSerializer):
    tick_id = serializers.IntegerField()
    dttm = serializers.DateTimeField(required=False)

    class Meta:
        model = TickPhoto
        fields = ['tick_id', 'type', 'image', 'dttm']


class DownloadTickPhotoExcelSerializer(serializers.Serializer):
    dt_from = serializers.DateField(required=False)
    dt_to = serializers.DateField(required=False)
