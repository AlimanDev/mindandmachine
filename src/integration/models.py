from django.db import models
from src.base.models import Shop, User
from src.base.models_abstract import AbstractModel, AbstractCodeNamedModel


class ExternalSystem(AbstractCodeNamedModel):
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
