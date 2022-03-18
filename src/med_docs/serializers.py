from rest_framework import serializers

from .models import (
    MedicalDocumentType,
    MedicalDocument,
)


class MedicalDocumentTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MedicalDocumentType
        fields = (
            'id',
            'code',
            'name',
        )


class MedicalDocumentSerializer(serializers.ModelSerializer):
    employee_id = serializers.IntegerField(required=False)
    medical_document_type_id = serializers.IntegerField(required=False)

    class Meta:
        model = MedicalDocument
        fields = (
            'id',
            'employee_id',
            'medical_document_type_id',
            'dt_from',
            'dt_to',
        )
