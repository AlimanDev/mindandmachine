from rest_framework import serializers

import pytz
from django.utils import six
from src.base.models import Shop
from src.base.fields import CurrentUserNetwork
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

    timezone = TimeZoneField()
    class Meta:
        model = Shop
        fields = ['id', 'parent_id', 'parent_code', 'name', 'settings_id', 'tm_shop_opens', 'tm_shop_closes', 
                'code', 'address', 'type', 'dt_opened', 'dt_closed', 'timezone', 'region_id', 
                'network_id', 'restricted_start_times','restricted_end_times', 'exchange_settings_id', 'load_template_id']


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
