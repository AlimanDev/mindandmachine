import binascii
import os
import uuid

from django.conf import settings
from django.utils.translation import gettext as _
from django.db import models
from django.utils.html import format_html
from django.utils.timezone import now
from django.utils.translation import gettext_lazy
from rest_framework.serializers import ValidationError

from src.base.models_abstract import AbstractActiveModel, AbstractActiveNetworkSpecificCodeNamedModel
from src.timetable.models import User, Shop, Employee


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


class TickPoint(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta:
        verbose_name = 'Точка отметки'
        verbose_name_plural = 'Точки отметок'

    USERNAME_FIELD = 'key'
    REQUIRED_FIELDS = []
    is_anonymous = False
    is_authenticated = True

    id = models.AutoField(primary_key=True)
    shop = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT)
    key = models.UUIDField(default=uuid.uuid4, unique=True)

    def __str__(self):
        return "{} {}".format(self.id, self.name)


class Tick(AbstractActiveModel):
    class Meta(object):
        verbose_name = 'Отметка'
        verbose_name_plural = 'Отметки'

    TYPE_COMING = 'C'
    TYPE_LEAVING = 'L'
    TYPE_BREAK_START = 'S'
    TYPE_BREAK_END = 'E'
    TYPE_NO_TYPE = 'N'

    RECORD_TYPES = (
        (TYPE_COMING, 'coming'),
        (TYPE_LEAVING, 'leaving'),
        (TYPE_BREAK_START, 'break start'),
        (TYPE_BREAK_END, 'break_end'),
        (TYPE_NO_TYPE, 'no_type'),
    )

    id = models.AutoField(primary_key=True)
    dttm = models.DateTimeField()
    user = models.ForeignKey(User, on_delete=models.PROTECT, null=False, )  # todo: make immutable
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, null=True, blank=True)
    tick_point = models.ForeignKey(TickPoint, null=False, blank=False, on_delete=models.PROTECT,
                                   related_query_name="ticks")
    # worker_day = models.ForeignKey(WorkerDay, null=True, blank=True, on_delete=models.SET_NULL, related_query_name="ticks")
    type = models.CharField(max_length=1, choices=RECORD_TYPES)
    lateness = models.DurationField(null=True)
    verified_score = models.FloatField(default=0)
    is_front = models.BooleanField(default=False)

    def test_img(self):
        return b'', ''

    @property
    def min_liveness_prop(self):
        if hasattr(self, 'min_liveness'):
            return self.min_liveness

        if hasattr(self, 'tickphotos_list'):
            liveness_list = [tickphoto.liveness for tickphoto in self.tickphotos_list if tickphoto.liveness]
            if liveness_list:
                return min(liveness_list)
            return

        self.tickphotos_list = list(self.tickphoto_set.all())
        return self.min_liveness_prop

    def get_tick_photo(self, type):
        if hasattr(self, 'tickphotos_list'):
            for tickphoto in self.tickphotos_list:
                if tickphoto.type == type:
                    return tickphoto
            return

        self.tickphotos_list = list(self.tickphoto_set.all())
        return self.get_tick_photo(type)

    @property
    def type_display(self):
        return self.get_type_display()

    def _get_img(self, type):
        tick_photo = self.get_tick_photo(type)
        if tick_photo:
            return (tick_photo.image, 'image/png')

        return (b'', 'image/png')

    @property
    def image_first(self):
        return self._get_img(TickPhoto.TYPE_FIRST)

    @property
    def image_self(self):
        return self._get_img(TickPhoto.TYPE_SELF)

    @property
    def image_last(self):
        return self._get_img(TickPhoto.TYPE_LAST)

    def image_tag_first(self):
        return self.image_tag(TickPhoto.TYPE_FIRST)

    def image_tag_last(self):
        return self.image_tag(TickPhoto.TYPE_LAST)

    def image_tag_self(self):
        return self.image_tag(TickPhoto.TYPE_SELF)

    def image_tag(self, type):
        tickphoto = self.get_tick_photo(type)
        if tickphoto:
            return format_html('<a href="{0}"> <img src="{0}", height="150" /></a>'.format(tickphoto.image.url))
        return ''

    @property
    def first_tick_photo_image_url(self):
        tick_photo = self.get_tick_photo(TickPhoto.TYPE_FIRST)
        if tick_photo:
            return settings.EXTERNAL_HOST + tick_photo.image.url

    @property
    def last_tick_photo_image_url(self):
        tick_photo = self.get_tick_photo(TickPhoto.TYPE_LAST)
        if tick_photo:
            return settings.EXTERNAL_HOST + tick_photo.image.url

    @property
    def self_tick_photo_image_url(self):
        tick_photo = self.get_tick_photo(TickPhoto.TYPE_SELF)
        if tick_photo:
            return settings.EXTERNAL_HOST + tick_photo.image.url


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


class ShopIpAddress(models.Model):
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    tick_point = models.ForeignKey(TickPoint, on_delete=models.SET_NULL, null=True, blank=True)
    ip_address = models.GenericIPAddressField(unique=True)
    is_authenticated = True
    is_anonymous = False
    USERNAME_FIELD = 'ip_address'
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        if self.tick_point and self.tick_point.shop_id != self.shop_id:
            raise ValidationError(_('Shop in tick point must be equal to shop in this record.'))
        return super().save(*args, **kwargs)
    
    @property
    def network_id(self):
        return self.shop.network_id
    
    @property
    def network(self):
        return self.shop.network
    
    @property
    def tick_point_obj(self):
        tick_point = self.tick_point
        if not tick_point:
            shop_id = self.shop_id
            tick_point = TickPoint.objects.filter(shop_id=shop_id, dttm_deleted__isnull=True).first()
            if tick_point is None:
                tick_point = TickPoint.objects.create(name=f'autocreate tickpoint {shop_id}', shop_id=shop_id)
        return tick_point
