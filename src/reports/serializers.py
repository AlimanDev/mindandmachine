from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class ValidateMixin:
    def _validate_ids_value(self, data, name):
        if name in data:
            data[name] = list(map(int, data[name].split(',')))
        return data
    
    def _validate_bool_value(self, data, name):
        if name in data:
            data[name] = bool(data[name])
        return data


class ReportFilterSerializer(serializers.Serializer, ValidateMixin):
    shop_ids = serializers.CharField(required=False)
    employee_ids = serializers.CharField(required=False)
    user_ids = serializers.CharField(required=False)
    is_vacancy = serializers.IntegerField(required=False)
    is_outsource = serializers.IntegerField(required=False)
    network_ids = serializers.CharField(required=False)
    work_type_name = serializers.ListField(required=False)
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()

    def validate(self, attrs):
        attrs = super().validate(attrs)

        attrs = self._validate_ids_value(attrs, 'shop_ids')
        attrs = self._validate_ids_value(attrs, 'employee_ids')
        attrs = self._validate_ids_value(attrs, 'user_ids')
        attrs = self._validate_ids_value(attrs, 'network_ids')
        attrs = self._validate_bool_value(attrs, 'is_vacancy')
        attrs = self._validate_bool_value(attrs, 'is_outsource')

        return attrs


class ConsolidatedTimesheetReportSerializer(serializers.Serializer):
    shop_id__in = serializers.CharField()
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    group_by = serializers.ChoiceField(choices=['employee', 'employee_position', 'position'], allow_blank=False)

    def validate(self, attrs):
        attrs['group_by'] = attrs['group_by'].split('_')
        return attrs


class TikReportSerializer(serializers.Serializer):
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    shop_id__in = serializers.ListField(child=serializers.IntegerField(min_value=1))
    employee_id__in = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    with_biometrics = serializers.BooleanField(default=False)
    emails = serializers.ListField(child=serializers.EmailField(), required=False)

    def validate(self, data):
        if data['dt_to'] < data['dt_from']:
            raise serializers.ValidationError(_('Invalid time period.'))
        if (data['dt_to']-data['dt_from']).days > 31:
            raise serializers.ValidationError(_('Time period must be within 31 days.'))
        return data
