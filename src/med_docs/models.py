from django.db import models

from src.base.models_abstract import AbstractModel, AbstractCodeNamedModel


class MedicalDocumentType(AbstractCodeNamedModel):
    pass


class MedicalDocument(AbstractModel):
    employee = models.ForeignKey(
        'base.Employee', on_delete=models.CASCADE, related_name='medical_documents')
    medical_document_type = models.ForeignKey(
        'med_docs.MedicalDocumentType', on_delete=models.PROTECT)
    dt_from = models.DateField()
    dt_to = models.DateField()
