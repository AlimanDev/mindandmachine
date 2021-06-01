from rest_framework import serializers
from rest_framework.validators import UniqueTogetherValidator

from src.timetable.models import EmploymentWorkType


class EmploymentWorkTypeListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    work_type_id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    period = serializers.IntegerField()
    bills_amount = serializers.IntegerField()
    priority = serializers.IntegerField()
    duration = serializers.FloatField()


class EmploymentWorkTypeSerializer(serializers.ModelSerializer):
    employment_id = serializers.IntegerField(required=False)
    work_type_id = serializers.IntegerField(required=False)

    class Meta:
        model = EmploymentWorkType
        fields = ['id', 'work_type_id', 'employment_id', 'period', 'bills_amount', 'priority', 'duration']
        validators = [
            UniqueTogetherValidator(
                queryset=EmploymentWorkType.objects.all(),
                fields=['work_type_id', 'employment_id'],
            ),
        ]
