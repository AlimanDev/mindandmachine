from django.db import models

from src.base.models_abstract import AbstractModel, AbstractCodeNamedModel


class MedicalDocumentType(AbstractCodeNamedModel):
    class Meta:
        verbose_name = 'Тип медицинского документа'
        verbose_name_plural = 'Типы медицинских документов'


class MedicalDocument(AbstractModel):
    employee = models.ForeignKey(
        'base.Employee', on_delete=models.CASCADE, related_name='medical_documents', verbose_name='Сотрудник')
    medical_document_type = models.ForeignKey(
        'med_docs.MedicalDocumentType', on_delete=models.PROTECT, verbose_name='Тип медицинского документа')
    dt_from = models.DateField(verbose_name='Дата "с" (включительно)')
    dt_to = models.DateField(verbose_name='Дата "по" (включительно)')

    class Meta:
        verbose_name = 'Период актуальности медицинского документа'
        verbose_name_plural = 'Периоды актуальности медицинского документа'
