from rest_framework import serializers, permissions
from src.timetable.models import ExchangeSettings
from src.base.views_abstract import BaseModelViewSet


# Serializers define the API representation.
class ExchangeSettingsSerializer(serializers.ModelSerializer):
    constraints = serializers.JSONField(required=False)
    class Meta:
        model = ExchangeSettings
        fields = '__all__'



class ExchangeSettingsViewSet(BaseModelViewSet):
    
    permission_classes = [permissions.IsAuthenticated]
    serializer_class = ExchangeSettingsSerializer
    

    def get_queryset(self):

        return ExchangeSettings.objects.filter(
            network_id=self.request.user.network_id,
        )

