from rest_framework import serializers
import json
import pytz
from django.utils import six
from src.base.models import Shop
from src.base.fields import CurrentUserNetwork
from src.base.exceptions import MessageError
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
    timezone = TimeZoneField()
    class Meta:
        model = Shop
        fields = ['id', 'parent_id', 'parent_code', 'name', 'settings_id', 'tm_open_dict', 'tm_close_dict',
                'code', 'address', 'type', 'dt_opened', 'dt_closed', 'timezone', 'region_id', 
                'network_id', 'restricted_start_times','restricted_end_times', 'exchange_settings_id', 'load_template_id', 'area', 'forecast_step_minutes']

    def to_representation(self, instance):
        data = super().to_representation(instance)
        data['tm_open_dict'] = instance.open_times
        data['tm_close_dict'] = instance.close_times
        return data

    def is_valid(self, *args, **kwargs):
        super().is_valid(*args, **kwargs)

        def validate_time(data):
            for key, value in data.items():
                if not (key in POSSIBLE_KEYS):
                    raise MessageError(code='time_shop_error_in_time_keys', params={'possible_keys': ', '.join(POSSIBLE_KEYS), 'key': key}, lang=self.context['request'].user.lang)
            try:
                Converter.parse_time(value)
            except:
                raise MessageError(code='time_shop_error_in_times', params={'time': value, 'key': key, 'format': QOS_TIME_FORMAT}, lang=self.context['request'].user.lang)
            
        if self.validated_data.get('tm_open_dict'):
            validate_time(self.validated_data.get('tm_open_dict'))
        
        if self.validated_data.get('tm_close_dict'):
            validate_time(self.validated_data.get('tm_close_dict'))
        
        self.validated_data['tm_open_dict'] = json.dumps(self.validated_data.get('tm_open_dict'))
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
