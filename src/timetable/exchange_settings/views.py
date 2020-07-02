from rest_framework import serializers, viewsets, permissions
from src.timetable.models import ExchangeSettings
from django_filters.rest_framework import FilterSet


# Serializers define the API representation.
class ExchangeSettingsSerializer(serializers.ModelSerializer):
    constraints = serializers.JSONField()
    class Meta:
        model = ExchangeSettings
        fields = '__all__'


class ExchangeSettingsFilter(FilterSet):
    class Meta:
        model = ExchangeSettings
        fields = {
            'network_id': ['exact', 'in'],
        }


class ExchangeSettingsViewSet(viewsets.ModelViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ExchangeSettingsSerializer
    queryset = ExchangeSettings.objects.all()


