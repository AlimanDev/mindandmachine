from django.contrib import admin

from .models import (
    MedicalDocumentType,
    MedicalDocument,
)


@admin.register(MedicalDocumentType)
class MedicalDocumentTypeAdmin(admin.ModelAdmin):
    pass


@admin.register(MedicalDocument)
class MedicalDocumentAdmin(admin.ModelAdmin):
    raw_id_fields = (
        'employee',
        'medical_document_type',
    )
