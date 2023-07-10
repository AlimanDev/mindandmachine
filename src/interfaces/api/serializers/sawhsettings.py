from django.conf import settings
from django.utils.translation import gettext_lazy as _

from rest_framework import serializers
from rest_framework.exceptions import ValidationError


class SAWHSettingsDailySerializer(serializers.Serializer):
    dt_from = serializers.DateField(format=settings.QOS_DATE_FORMAT, required=False)
    dt_to = serializers.DateField(format=settings.QOS_DATE_FORMAT, required=False)

    def validate(self, data) -> bool:
        if data.get('dt_from') and data.get('dt_to') and data['dt_to'] < data['dt_from']:
            raise ValidationError(_("Invalid time period."))
        return data
