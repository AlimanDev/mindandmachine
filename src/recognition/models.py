import binascii
import os
import uuid

from django.db import models
from django.utils.timezone import now
from django.utils.translation import gettext_lazy

from src.base.models_abstract import AbstractActiveModel, AbstractActiveNamedModel
from src.timetable.models import User, Shop


def user_directory_path(instance, filename):
    date = str(now().date())
    ext = filename.split('.')[-1]
    return 'user_photo/{}/{}.{}'.format(date, uuid.uuid4().hex, ext)


class UserConnecter(AbstractActiveModel):
    class Meta(object):
        verbose_name = 'Сопоставление пользователей'
        verbose_name_plural = 'Сопоставления пользователей'

    user = models.OneToOneField(User, on_delete=models.PROTECT, primary_key=True)
    partner_id = models.IntegerField(null=False)


class TickPoint(AbstractActiveNamedModel):
    class Meta(object):
        verbose_name = 'Точка отметки'
        verbose_name_plural = 'Точки отметок'

    USERNAME_FIELD = 'key'
    REQUIRED_FIELDS = []
    is_anonymous = False
    is_authenticated = True

    id = models.AutoField(primary_key=True)
    name = models.CharField(max_length=128, null=True, blank=True)
    title = models.CharField(max_length=64)  # TODO: перенести title в name, сделать name обяз., удалить title
    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)
    key = models.UUIDField(default=uuid.uuid4, unique=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return "{} {}".format(self.id, self.title)


class Tick(AbstractActiveModel):
    class Meta(object):
        verbose_name = 'Отметка'
        verbose_name_plural = 'Отметки'

    TYPE_COMING = 'C'
    TYPE_LEAVING = 'L'
    TYPE_BREAK_START = 'S'
    TYPE_BREAK_END = 'E'

    RECORD_TYPES = (
        (TYPE_COMING, 'coming'),
        (TYPE_LEAVING, 'leaving'),
        (TYPE_BREAK_START, 'break start'),
        (TYPE_BREAK_END, 'break_end')
    )

    id = models.AutoField(primary_key=True)
    dttm = models.DateTimeField()
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, )  # todo: make immutable
    tick_point = models.ForeignKey(TickPoint, null=False, blank=False, on_delete=models.PROTECT,
                                   related_query_name="ticks")
    # worker_day = models.ForeignKey(WorkerDay, null=True, blank=True, on_delete=models.SET_NULL, related_query_name="ticks")
    type = models.CharField(max_length=1, choices=RECORD_TYPES)
    lateness = models.DurationField(null=True)
    verified_score = models.FloatField(default=0)
    is_front = models.BooleanField(default=False)


class TickPhoto(AbstractActiveModel):
    class Meta(object):
        verbose_name = 'Фотографии отметок'
        verbose_name_plural = 'Фотографии отметок'

    TYPE_SELF = 'S'
    TYPE_FIRST = 'F'
    TYPE_LAST = 'L'

    RECORD_TYPES = (
        (TYPE_SELF, 'self'),
        (TYPE_FIRST, 'first'),
        (TYPE_LAST, 'last'),
    )

    id = models.AutoField(primary_key=True)
    tick = models.ForeignKey(Tick, on_delete=models.PROTECT, null=False)
    dttm = models.DateTimeField()
    verified_score = models.FloatField(default=0)
    image = models.ImageField(null=False, blank=False, upload_to=user_directory_path)
    type = models.CharField(max_length=1, choices=RECORD_TYPES)
    lateness = models.DurationField(null=True)
    liveness = models.FloatField(null=True)
    is_front = models.BooleanField(default=False)


class TickPointToken(models.Model):
    key = models.CharField(gettext_lazy("Key"), max_length=40, primary_key=True)
    user = models.OneToOneField(
        TickPoint, related_name='token',
        on_delete=models.CASCADE,
    )
    created = models.DateTimeField(gettext_lazy("Created"), auto_now_add=True)

    def save(self, *args, **kwargs):
        if not self.key:
            self.key = self.generate_key()
        return super().save(*args, **kwargs)

    def generate_key(self):
        return binascii.hexlify(os.urandom(20)).decode()

    def __str__(self):
        return self.key
