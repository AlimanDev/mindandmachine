from django.db import models
from django.utils import timezone

class AbstractModelManager(models.Manager):
    pass



class AbstractModel(models.Model):
    """
    Базовая абстрактная модель. От нее должны быть наследованы все сущности (модели)

    """
    class Meta:
        abstract = True

    objects = AbstractModelManager()


class AbstractActiveModelManager(AbstractModelManager):
    def qos_filter_active(self, dt_from, dt_to, *args, **kwargs):
        """
        added earlier then dt_from, deleted later then dt_to
        :param dt_from:
        :param dt_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            models.Q(dttm_added__date__lte=dt_to) | models.Q(dttm_added__isnull=True)
        ).filter(
            models.Q(dttm_deleted__date__gt=dt_from) | models.Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)

    def qos_delete(self, *args, **kwargs):
        return self.filter(*args, **kwargs).update(dttm_deleted=timezone.now())


class AbstractActiveModel(AbstractModel):
    """
    Модель, у которой есть время жизни, то есть время создания и время удаления

    """

    class Meta:
        abstract = True

    dttm_added = models.DateTimeField(default=timezone.now)
    dttm_deleted = models.DateTimeField(null=True, blank=True)

    def delete(self):
        self.dttm_deleted = timezone.now()
        self.save()

        return self

    # dttm_modified = models.DateTimeField(null=True, blank=True)
    # changed_by = models.IntegerField(null=True, blank=True)  # вообще на User ссылка

    objects = AbstractActiveModelManager()


class AbstractActiveNamedModelManager(AbstractModelManager):
    pass


class AbstractActiveNamedModel(AbstractActiveModel):
    """
    Именованная модель с  кодом для синхронизации

    """
    class Meta:
        abstract = True
        unique_together = (('code', 'network'),)

    name = models.CharField(max_length=128)
    code = models.CharField(max_length=64, null=True, blank=True)
    network = models.ForeignKey('base.Network', on_delete=models.PROTECT, null=True)

    objects = AbstractActiveNamedModelManager()

    def __str__(self):
        return f'name: {self.name}, code: {self.code}'

