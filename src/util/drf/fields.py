from rest_framework import serializers


class RoundingDecimalField(serializers.DecimalField):
    def validate_precision(self, value):
        return value
