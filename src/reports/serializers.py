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
