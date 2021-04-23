import datetime
import json

import geopy.distance
import pytz
from django.utils import six
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from src.base.fields import CurrentUserNetwork
from src.base.models import Shop, ShopSchedule
from src.conf.djconfig import QOS_TIME_FORMAT
from src.util.drf.fields import RoundingDecimalField
from src.util.models_converter import Converter
from src.timetable.worker_day.tasks import recalc_wdays

POSSIBLE_KEYS = [
    '0', '1', '2', '3', '4', '5', '6', 'all',
    'd0', 'd1', 'd2', 'd3', 'd4', 'd5', 'd6',
]


class TimeZoneField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(pytz.common_timezones + [(None, "")], **kwargs)

    def to_representation(self, value):
        return str(six.text_type(super().to_representation(value)))


class RestrictedTimeValidator:
    error_messages = {
        'invalid_time_format': _('Invalid time format. Format should be {format}'),
    }
    format = '%H:%M'

    def __call__(self, value):
        restricted_times = json.loads(value)
        for time_str in restricted_times:
            try:
                datetime.datetime.strptime(time_str, self.format)
            except (ValueError, TypeError):
                raise serializers.ValidationError(self.error_messages['invalid_time_format'].format(format=self.format))


class NonstandardShopScheduleSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopSchedule
        fields = (
            'dt',
            'type',
            'opens',
            'closes',
        )


def serialize_shop(shop: Shop, request):
    distance = None
    if request:
        lat = request.META.get('X-LAT')
        lon = request.META.get('X-LON')
        if lat and lon and shop.latitude and shop.longitude:
            distance = round(geopy.distance.distance((lat, lon), (shop.latitude, shop.longitude)).km, 2)
    return {
        'id': shop.id,
        'name': shop.name,
        'forecast_step_minutes': shop.forecast_step_minutes,
        'tm_open_dict': shop.open_times,
        'tm_close_dict': shop.close_times,
        'address': shop.address,
        'timezone': str(six.text_type(shop.timezone)),
        'code': shop.code,
        'longitude': shop.longitude,
        'latitude': shop.latitude,
        'settings_id': shop.settings_id,
        'load_template_id': shop.load_template_id,
        'parent_id': shop.parent_id,
        'distance': distance,
    }


class ShopSerializer(serializers.ModelSerializer):
    parent_id = serializers.IntegerField(required=False)
    parent_code = serializers.CharField(required=False)
    region_id = serializers.IntegerField(required=False)
    network_id = serializers.HiddenField(default=CurrentUserNetwork())
    exchange_settings_id = serializers.IntegerField(required=False)
    load_template_id = serializers.IntegerField(required=False)
    settings_id = serializers.IntegerField(required=False)
    tm_open_dict = serializers.JSONField(required=False)
    tm_close_dict = serializers.JSONField(required=False)
    nonstandard_schedule = NonstandardShopScheduleSerializer(
        many=True, allow_null=True, required=False, write_only=True)
    load_template_status = serializers.CharField(read_only=True)
    timezone = TimeZoneField(required=False)
    is_active = serializers.BooleanField(required=False, default=True)
    director_code = serializers.CharField(required=False)
    distance = serializers.SerializerMethodField(label='Расстояние до магазина (км)')
    latitude = RoundingDecimalField(decimal_places=8, max_digits=12, allow_null=True, required=False)
    longitude = RoundingDecimalField(decimal_places=8, max_digits=12, allow_null=True, required=False)

    def get_distance(self, shop):
        if self.context.get('request', False):
            lat = self.context.get('request').META.get('X-LAT')
            lon = self.context.get('request').META.get('X-LON')
            if lat and lon and shop.latitude and shop.longitude:
                return round(geopy.distance.distance((lat, lon), (shop.latitude, shop.longitude)).km, 2)

    class Meta:
        model = Shop
        fields = ['id', 'parent_id', 'parent_code', 'name', 'settings_id', 'tm_open_dict', 'tm_close_dict',
                  'code', 'address', 'type', 'dt_opened', 'dt_closed', 'timezone', 'region_id',
                  'network_id', 'restricted_start_times', 'restricted_end_times', 'exchange_settings_id',
                  'load_template_id', 'area', 'forecast_step_minutes', 'load_template_status', 'is_active',
                  'director_code', 'latitude', 'longitude', 'director_id', 'distance', 'nonstandard_schedule', 'email',
                  'fias_code',]
        extra_kwargs = {
            'restricted_start_times': {
                'validators': [RestrictedTimeValidator()]
            },
            'restricted_end_times': {
                'validators': [RestrictedTimeValidator()]
            },
        }

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['tm_open_dict'] = instance.open_times
        data['tm_close_dict'] = instance.close_times
        return data

    def __init__(self, *args, **kwargs):
        super(ShopSerializer, self).__init__(*args, **kwargs)
        if self.context.get('request', False):
            self.fields['code'].validators.append(
                UniqueValidator(
                    Shop.objects.filter(network=self.context.get('request').user.network)
                )
            )

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)

        def validate_time(data):
            for key, value in data.items():
                if not (key in POSSIBLE_KEYS):
                    raise serializers.ValidationError(_('Invalid key value {key}. Allowed values: {possible_keys}.').format(possible_keys=', '.join(POSSIBLE_KEYS), key=key))
            try:
                Converter.parse_time(value)
            except:
                raise serializers.ValidationError(_('Invalid time format {time} for value {key}. The format must be {format}.').format(time=value, key=key, format=QOS_TIME_FORMAT))

        if self.validated_data.get('tm_open_dict'):
            validate_time(self.validated_data.get('tm_open_dict'))
        if self.validated_data.get('tm_close_dict'):
            validate_time(self.validated_data.get('tm_close_dict'))

        if 'tm_open_dict' in self.validated_data:
            self.validated_data['tm_open_dict'] = json.dumps(self.validated_data.get('tm_open_dict'))
        if 'tm_close_dict' in self.validated_data:
            self.validated_data['tm_close_dict'] = json.dumps(self.validated_data.get('tm_close_dict'))

        return True

    def _update_or_create_nested_data(self, instance, nonstandard_schedule):
        if nonstandard_schedule:
            user = getattr(self.context.get('request', {}), 'user', None)
            dates = [sch['dt'] for sch in nonstandard_schedule]
            ss_dict = {}
            for ss in ShopSchedule.objects.filter(shop=instance, dt__in=dates):
                ss_dict[ss.dt] = ss

            for sch_dict in nonstandard_schedule:
                ss = ss_dict.get(sch_dict['dt'])
                if ss is None:
                    ss = ShopSchedule(
                        shop=instance,
                        dt=sch_dict['dt'],
                        type=sch_dict['type'],
                        opens=sch_dict['opens'],
                        closes=sch_dict['closes'],
                        modified_by=self.context.get('request').user if 'request' in self.context else None,
                    )
                    ss.save(recalc_wdays=True)
                    continue

                if ss.type != sch_dict['type'] or ss.opens != sch_dict['opens'] or ss.closes != sch_dict['closes'] \
                        or ss.modified_by != user:
                    ShopSchedule.objects.update_or_create(
                        shop=instance,
                        dt=sch_dict['dt'],
                        defaults=dict(
                            type=sch_dict['type'],
                            opens=sch_dict['opens'],
                            closes=sch_dict['closes'],
                            modified_by=user,
                        )
                    )
                    dt_str = Converter.convert_date(sch_dict['dt'])
                    recalc_wdays.delay(
                        shop_id=instance.id,
                        dt__gte=dt_str,
                        dt__lte=dt_str,
                    )

    def create(self, validated_data):
        nonstandard_schedule = validated_data.pop('nonstandard_schedule', [])
        shop = super(ShopSerializer, self).create(validated_data)
        self._update_or_create_nested_data(shop, nonstandard_schedule)
        return shop

    def update(self, instance, validated_data):
        nonstandard_schedule = validated_data.pop('nonstandard_schedule', [])
        shop = super(ShopSerializer, self).update(instance, validated_data)
        self._update_or_create_nested_data(shop, nonstandard_schedule)
        return shop


class ShopStatSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    parent_id = serializers.IntegerField()
    name = serializers.CharField()
    fot_curr = serializers.FloatField()
    fot_prev = serializers.FloatField()
    revenue_prev = serializers.FloatField()
    revenue_curr = serializers.FloatField()
    lack_prev = serializers.FloatField()
    lack_curr = serializers.FloatField()
