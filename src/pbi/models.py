from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.db.models import Q, Case, When, BooleanField

from src.base.models import (
    User,
    Group,
)
from src.base.models_abstract import AbstractModel


class Report(AbstractModel):
    name = models.CharField(max_length=256)
    tenant_id = models.CharField(max_length=128)
    client_id = models.CharField(max_length=128)
    client_secret = models.CharField(max_length=128)
    workspace_id = models.CharField(max_length=128)
    report_id = models.CharField(max_length=512)

    class Meta:
        verbose_name = 'Отчет'
        verbose_name_plural = 'Отчеты'

    def __str__(self):
        return self.name


class ReportPermission(AbstractModel):
    report = models.ForeignKey('pbi.Report', on_delete=models.CASCADE)
    group = models.OneToOneField('base.Group', on_delete=models.CASCADE, null=True, blank=True)
    user = models.OneToOneField('base.User', on_delete=models.CASCADE, null=True, blank=True)
    use_rls = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Доступ к отчету'
        verbose_name_plural = 'Доступы к отчетам'

    def __str__(self):
        obj = self.user if self.user_id else self.group
        return f'{obj} - {self.report.name}'

    def clean(self):
        if not (self.user_id or self.group_id):
            raise DjangoValidationError('Необходимо выбрать либо пользователя, либо группу')

        if self.user_id and self.group_id:
            raise DjangoValidationError('Нельзя одновременно выбрать и пользователя и группу')

    @classmethod
    def get_report_perm(cls, user):
        return cls.objects.filter(
            Q(user=user) | Q(group__in=user.get_group_ids()),
        ).annotate(
            is_user_equal=Case(
                When(user_id=user.id, then=True),
                default=False, output_field=BooleanField()
            )
        ).order_by(
            '-is_user_equal'
        ).select_related(
            'report',
        ).first()
