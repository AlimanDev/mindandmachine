from rest_framework import serializers
from rest_framework.exceptions import ValidationError

from src.base.models import Employment
from src.timetable.models import WorkerConstraint


class WorkerConstraintSerializer(serializers.ModelSerializer):
    id = serializers.IntegerField(required=False)

    class Meta:
        model = WorkerConstraint
        fields = ['id', 'employment_id', 'weekday', 'is_lite', 'tm']
        extra_kwargs = {
            'employment_id': {
                'read_only': True,
            }
        }


class WrappedWorkerConstraintSerializer(serializers.Serializer):
    data = WorkerConstraintSerializer(many=True, )

    def create(self, validated_data):
        validated_data = validated_data.get('data')
        employment_id = self.context.get('view').kwargs.get('employment_pk')
        employment = Employment.objects.get(id=employment_id)
        to_create = []
        ids = []

        constraints = WorkerConstraint.objects.filter(
            employment_id=employment_id,
        )
        constraint_mapping = {constraint.id: constraint for constraint in constraints}

        wc_serializer = WorkerConstraintSerializer()
        for item in validated_data:
            if item.get('id'):
                if not constraint_mapping.get(item['id']):
                    raise ValidationError({"error": f"object with id {item['id']} does not exist"})
                wc_serializer.update(constraint_mapping[item['id']], item)
                ids.append(item['id'])
            else:
                constraint = WorkerConstraint(
                    **item,
                    employment_id=employment_id,
                    shop_id=employment.shop_id,
                )
                to_create.append(constraint)

        WorkerConstraint.objects.filter(
            employment_id=employment_id
        ).exclude(
            id__in=ids
        ).delete()

        WorkerConstraint.objects.bulk_create(to_create)
        return {'data': WorkerConstraint.objects.filter(employment_id=employment_id)}


class WorkerConstraintListSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    employment_id = serializers.IntegerField()
    weekday = serializers.IntegerField()
    is_lite = serializers.BooleanField()
    tm = serializers.TimeField()
