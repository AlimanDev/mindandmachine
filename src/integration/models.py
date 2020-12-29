from django.db import models
from src.base.models import Shop, User
from src.base.models_abstract import AbstractModel, AbstractActiveNamedModel


class ExternalSystem(AbstractActiveNamedModel):
    class Meta:
        verbose_name = 'Связь с внешними системами'
        verbose_name_plural = 'Связи с внешними системами'


class ShopExternalCode(AbstractModel):
    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    code = models.CharField(null=False, blank=False, max_length=64)


class UserExternalCode(AbstractModel):
    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    code = models.CharField(null=False, blank=False, max_length=64)
