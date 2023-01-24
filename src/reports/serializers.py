from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class CustomSerializer(serializers.Serializer):
    def validate(self, attrs):
        attrs = super().validate(attrs)
        self._validate_list_char_integers(attrs)
        self._validate_list_char_strings(attrs)
        self._validate_bool_values(attrs)
        return attrs

    def _validate_list_char_integers(self, data):
        """Multiple integers in comma-separated `CharField`"""
        meta = getattr(self, 'Meta', None)
        for field in getattr(meta, 'list_char_integers_fields', []):
            if field in data:
                data[field] = list(map(int, data[field].split(',')))

    def _validate_list_char_strings(self, data):
        """Multiple strings in comma-separated `CharField`"""
        meta = getattr(self, 'Meta', None)
        for field in getattr(meta, 'list_char_strings_fields', []):
            if field in data:
                data[field] = list(map(str, data[field].split(',')))

    def _validate_bool_values(self, data):
        """Fields that should evaluate to boolean"""
        meta = getattr(self, 'Meta', None)
        for field in getattr(meta, 'bool_fields', []):
            if field in data:
                data[field] = bool(data[field])


class ReportFilterSerializer(CustomSerializer):
    dt_from = serializers.DateField()
    dt_to = serializers.DateField()
    shop_id__in = serializers.CharField(required=False)
    employee_id__in = serializers.CharField(required=False)
    worker_id__in = serializers.CharField(required=False)
    is_vacancy = serializers.IntegerField(required=False)
    is_outsource = serializers.IntegerField(required=False)
    worker__network_id__in = serializers.CharField(required=False)
    work_type_name__in = serializers.CharField(required=False)
    emails = serializers.ListField(child=serializers.EmailField(), required=False)

    class Meta:
        list_char_integers_fields = ('shop_id__in', 'employee_id__in', 'worker_id__in', 'worker__network_id__in')
        list_char_strings_fields = ('work_type_name__in',)
        bool_fields = ('is_vacancy', 'is_outsource')

    def validate(self, attrs):
        if attrs['dt_to'] < attrs['dt_from']:
            raise serializers.ValidationError(_('Invalid time period.'))
        attrs = super().validate(attrs)
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
