from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from src.base.models import Shop, User
from src.base.models_abstract import AbstractModel, AbstractCodeNamedModel


class ExternalSystem(AbstractCodeNamedModel):
    class Meta:
        verbose_name = 'Внешняя система'
        verbose_name_plural = 'Внешние системы'


class AttendanceArea(AbstractCodeNamedModel):
    class Meta:
        verbose_name = 'Зона учета внешней системы'
        verbose_name_plural = 'Зоны учета внешней системы'

    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT)


class ShopExternalCode(AbstractModel):
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    attendance_area = models.ForeignKey(AttendanceArea, on_delete=models.PROTECT)


class UserExternalCode(AbstractModel):
    external_system = models.ForeignKey(ExternalSystem, on_delete=models.PROTECT)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    code = models.CharField(null=False, blank=False, max_length=64)


class GenericExternalCode(AbstractModel):
    external_system = models.ForeignKey(ExternalSystem, on_delete=models.CASCADE)
    code = models.CharField(max_length=64)
    object_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)  # TODO: виджет в админке поудобнее?
    object_id = models.PositiveIntegerField()
    object = GenericForeignKey('object_type', 'object_id')

    class Meta:
        unique_together = (
            ('code', 'external_system', 'object_type', 'object_id'),
        )

    def __str__(self):
        return '{} {} {}'.format(self.object, self.code, self.external_system)


class VMdaUsers(models.Model):
    code = models.TextField(primary_key=True)
    id = models.ForeignKey('base.User', db_column='id', on_delete=models.DO_NOTHING)
    username = models.TextField()
    last_name = models.TextField()
    first_name = models.TextField()
    middle_name = models.TextField()
    email = models.TextField()
    dt_hired = models.DateField()
    dt_fired = models.DateField()
    active = models.BooleanField()
    level = models.TextField()
    role = models.TextField()
    shop_name = models.TextField()
    shop_code = models.TextField()
    position_name = models.TextField()
    position_code = models.TextField()
    position_group_name = models.TextField()
    position_group_code = models.TextField()
    func_group_name = models.TextField()
    func_group_code = models.TextField()
    user_last_modified = models.DateTimeField()
    employment_last_modified = models.DateTimeField()
    position_last_modified = models.DateTimeField()
    last_modified = models.DateTimeField()

    class Meta:
        managed = False
        db_table = 'v_mda_users'

    def __str__(self):
        return self.username + ' ' + self.shop_code
