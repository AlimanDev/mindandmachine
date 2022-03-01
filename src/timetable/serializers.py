from django.utils.translation import gettext_lazy as _
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

    def validate(self, attrs):
        attrs = super().validate(attrs)
        check_priority_qs = EmploymentWorkType.objects.filter(
            employment_id=attrs['employment_id'],
            priority=attrs.get('priority', 1),
        )
        if self.instance:
            check_priority_qs = check_priority_qs.exclude(id=self.instance.id)
        
        if 'priority' in attrs and check_priority_qs.exists():
            raise serializers.ValidationError(_('Employment can have only one main type of work.'))

        return attrs
