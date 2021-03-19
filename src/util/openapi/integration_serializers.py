from rest_framework import serializers
import pytz
from src.util.drf.fields import RoundingDecimalField
from django.utils import six


class TimeZoneField(serializers.ChoiceField):
    def __init__(self, **kwargs):
        super().__init__(pytz.common_timezones + [(None, "")], **kwargs)

    def to_representation(self, value):
        return str(six.text_type(super().to_representation(value)))


class ShopIntegrationSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField()
    parent_code = serializers.CharField(required=False)
    timezone = TimeZoneField(required=False)
    by_code = serializers.BooleanField(default=True)
    tm_open_dict = serializers.JSONField(required=False, default={'d0': '10:00:00', 'd3': '11:00:00'})
    tm_close_dict = serializers.JSONField(required=False, default={'d0': '20:00:00', 'd3': '21:00:00'})
    latitude = RoundingDecimalField(decimal_places=6, max_digits=12, allow_null=True, required=False)
    longitude = RoundingDecimalField(decimal_places=6, max_digits=12, allow_null=True, required=False)
    email = serializers.EmailField(required=False)
