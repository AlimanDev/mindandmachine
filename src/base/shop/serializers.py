import datetime
import json

import geopy.distance
import pytz
from django.utils import six
from django.utils.translation import ugettext_lazy as _
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

from src.base.exceptions import MessageError
from src.base.fields import CurrentUserNetwork
from src.base.models import Shop
from src.conf.djconfig import QOS_TIME_FORMAT
from src.util.models_converter import Converter

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
    load_template_status = serializers.CharField(read_only=True)
    timezone = TimeZoneField(required=False)
    is_active = serializers.BooleanField(required=False, default=True)
    director_code = serializers.CharField(required=False)
    distance = serializers.SerializerMethodField(label='Расстояние до магазина (км)')

    def get_distance(self, shop):
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
                  'director_code', 'latitude', 'longitude', 'director_id', 'distance']
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
                    raise MessageError(code='time_shop_error_in_time_keys',
                                       params={'possible_keys': ', '.join(POSSIBLE_KEYS), 'key': key},
                                       lang=self.context['request'].user.lang)
            try:
                Converter.parse_time(value)
            except:
                raise MessageError(code='time_shop_error_in_times',
                                   params={'time': value, 'key': key, 'format': QOS_TIME_FORMAT},
                                   lang=self.context['request'].user.lang)

        if self.validated_data.get('tm_open_dict'):
            validate_time(self.validated_data.get('tm_open_dict'))
        if self.validated_data.get('tm_close_dict'):
            validate_time(self.validated_data.get('tm_close_dict'))

        if 'tm_open_dict' in self.validated_data:
            self.validated_data['tm_open_dict'] = json.dumps(self.validated_data.get('tm_open_dict'))
        if 'tm_close_dict' in self.validated_data:
            self.validated_data['tm_close_dict'] = json.dumps(self.validated_data.get('tm_close_dict'))

        return True


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
