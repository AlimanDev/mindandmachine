from django.db import models
from django.utils import timezone


class AbstractModelManager(models.Manager):
    pass


class AbstractModel(models.Model):
    """
    Базовая абстрактная модель. От нее должны быть наследованы все сущности (модели)

    """
    dttm_modified = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    objects = AbstractModelManager()


class NetworkSpecificModel(models.Model):
    network = models.ForeignKey('base.Network', on_delete=models.PROTECT, null=True)

    class Meta:
        abstract = True


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

    def delete(self, **kwargs):
        self.dttm_deleted = timezone.now()
        self.save()
        return self

    @property
    def is_active(self):
        dttm_now = timezone.now()
        return self.dttm_deleted is None or (self.dttm_added < dttm_now < self.dttm_deleted)

    @is_active.setter
    def is_active(self, val):
        if val:
            if self.dttm_deleted:
                self.dttm_deleted = None
        else:
            if not self.dttm_deleted:
                self.dttm_deleted = timezone.now()

    # dttm_modified = models.DateTimeField(null=True, blank=True)
    # changed_by = models.IntegerField(null=True, blank=True)  # вообще на User ссылка

    objects = AbstractActiveModelManager()


class AbstractNamedModel(models.Model):
    name = models.CharField(max_length=128, verbose_name='Имя')

    def __str__(self):
        return f'name: {self.name}'

    class Meta:
        abstract = True


class AbstractCodeNamedModel(AbstractNamedModel):
    code = models.CharField(max_length=64, null=True, blank=True, verbose_name='Код')

    def __str__(self):
        return f'name: {self.name}, code: {self.code}'

    class Meta:
        abstract = True


class AbstractActiveNamedModel(AbstractActiveModel, AbstractNamedModel):
    class Meta:
        abstract = True


class AbstractActiveNetworkSpecificCodeNamedModelManager(models.Manager):
    pass


class AbstractActiveNetworkSpecificCodeNamedModel(AbstractActiveModel, AbstractCodeNamedModel, NetworkSpecificModel):
    """
    Именованная модель с кодом для синхронизации
    """

    class Meta:
        abstract = True
        unique_together = (
            ('code', 'network'),
        )

    objects = AbstractActiveNetworkSpecificCodeNamedModelManager()
