import datetime
import json
from decimal import Decimal

import pandas as pd
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib.auth.models import (
    UserManager
)
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models
from django.db import transaction
from django.db.models import (
    Subquery, OuterRef, Max, Q, Case, When, Value, FloatField, F, IntegerField, Exists, BooleanField, Count, Sum,
    Prefetch,
)
from django.db.models.expressions import Func
from django.db.models.expressions import RawSQL
from django.db.models.fields import CharField
from django.db.models.fields import PositiveSmallIntegerField
from django.db.models.fields.json import JSONField
from django.db.models.functions import Abs, Cast, Extract, Least
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from rest_framework.exceptions import PermissionDenied, ValidationError

from src.base.models import Shop, Employment, User, Network, Break, ProductionDay, Employee, Group
from src.base.models_abstract import AbstractModel, AbstractActiveModel, AbstractActiveNetworkSpecificCodeNamedModel, \
    AbstractActiveModelManager
from src.events.signals import event_signal
from src.integration.mda.tmp_backport import ArraySubquery
from src.recognition.events import EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN
from src.tasks.models import Task
from src.timetable.break_time_subtractor import break_time_subtractor_map
from src.timetable.exceptions import (
    MainWorkHoursGreaterThanNorm,
    WorkTimeOverlap,
    WorkDayTaskViolation,
    MultipleWDTypesOnOneDateForOneEmployee,
    HasAnotherWdayOnDate,
)
from src.util.commons import obj_deep_get
from src.util.mixins.qs import AnnotateValueEqualityQSMixin
from src.util.time import _time_to_float


class WorkerManager(UserManager):
    pass


class WorkTypeManager(AbstractActiveModelManager):
    def qos_filter_active(self, dt_from, dt_to, *args, **kwargs):
        """
        added earlier then dt_from, deleted later then dt_to
        :param dttm_from:
        :param dttm_to:
        :param args:
        :param kwargs:
        :return:
        """

        return self.filter(
            Q(dttm_added__date__lte=dt_from) | Q(dttm_added__isnull=True)
        ).filter(
            Q(dttm_deleted__date__gte=dt_to) | Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)

    def qos_delete(self, *args, **kwargs):
        for obj in self.filter(*args, **kwargs):
            obj.delete()


class WorkTypeName(AbstractActiveNetworkSpecificCodeNamedModel):
    position = models.ForeignKey(
        'base.WorkerPosition', null=True, blank=True, on_delete=models.PROTECT,
        verbose_name='С какой должностью соотносится тип работ',
        help_text='Используется при формировании табеля для получения должности по типу работ, если включена настройка'
                  '"Получать должность по типу работ при формировании фактического табеля"'
    )

    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Название типа работ'
        verbose_name_plural = 'Названия типов работ'

    def delete(self):
        from src.forecast.models import OperationTypeName
        super(WorkTypeName, self).delete()
        WorkType.objects.qos_delete(work_type_name__id=self.pk)
        otn = OperationTypeName.objects.filter(work_type_name_id=self.pk).first()
        if otn:
            otn.delete()
        return self

    def __str__(self):
        return 'id: {}, name: {}, code: {}'.format(
            self.id,
            self.name,
            self.code,
        )

    def save(self, *args, **kwargs):
        from src.forecast.models import OperationTypeName
        is_new = self.id is None
        super().save(*args, **kwargs)
        update_or_create_kwargs = {}
        defaults = {
            'do_forecast': OperationTypeName.FORECAST_FORMULA,
            'code': self.code,
            'work_type_name_id': self.id,
            'name': self.name,
            'network_id': self.network_id,
            'dttm_deleted': None,
        }
        if is_new or not OperationTypeName.objects.filter(work_type_name_id=self.id).exists():
            update_or_create_kwargs['network_id'] = defaults.pop('network_id')
            if self.code:
                update_or_create_kwargs['code'] = defaults.pop('code')
            else:
                update_or_create_kwargs['name'] = defaults.pop('name')
        else:
            update_or_create_kwargs['work_type_name_id'] = defaults.pop('work_type_name_id')


        OperationTypeName.objects.update_or_create(
            **update_or_create_kwargs,
            defaults=defaults,
        )

    @classmethod
    def get_work_type_names_dict(cls):
        return {wtn.id: wtn for wtn in cls.objects.all()}


class WorkType(AbstractActiveModel):
    class Meta:
        verbose_name = 'Тип работ'
        verbose_name_plural = 'Типы работ'
        unique_together = ['shop', 'work_type_name']

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.work_type_name.name, self.shop.name, self.shop.parent.name if self.shop.parent else '', self.id)

    id = models.BigAutoField(primary_key=True)

    priority = models.PositiveIntegerField(default=100)  # 1--главная касса, 2--линия, 3--экспресс
    dttm_last_update_queue = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='work_types')
    work_type_name = models.ForeignKey(WorkTypeName, on_delete=models.PROTECT, related_name='work_types')
    min_workers_amount = models.IntegerField(default=0, blank=True, null=True)
    max_workers_amount = models.IntegerField(default=20, blank=True, null=True)
    preliminary_cost_per_hour = models.DecimalField(
        'Предварительная стоимость работ за час', max_digits=8, 
        decimal_places=2,
        null=True, blank=True,
    )

    probability = models.FloatField(default=1.0)
    prior_weight = models.FloatField(default=1.0)
    objects = WorkTypeManager()

    period_queue_params = models.CharField(
        max_length=1024,
        default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 1, "reg_lambda": 0.1, "silent": 1, "iterations": 20}'
    )

    def __init__(self, *args, **kwargs):
        code = kwargs.pop('code', None)
        super(WorkType, self).__init__(*args, **kwargs)
        if code:
            self.work_type_name = WorkTypeName.objects.get(code=code)

    def save(self, *args, **kwargs):
        from src.forecast.models import OperationType
        if hasattr(self, 'code'):
            self.work_type_name = WorkTypeName.objects.get(code=self.code)
        is_new = self.id is None
        super(WorkType, self).save(*args, **kwargs)
        update_or_create_kwargs = {}
        defaults = {
            'status': OperationType.UPDATED,
            'work_type_id': self.id,
            'dttm_deleted': None,
            'operation_type_name': self.work_type_name.operation_type_name,
            'shop_id': self.shop_id,
        }
        if is_new or not OperationType.objects.filter(work_type_id=self.id).exists():
            update_or_create_kwargs['shop_id'] = defaults.pop('shop_id')
            update_or_create_kwargs['operation_type_name'] = defaults.pop('operation_type_name')
        else:
            update_or_create_kwargs['work_type_id'] = defaults.pop('work_type_id')

        OperationType.objects.update_or_create(
            **update_or_create_kwargs,
            defaults=defaults,
        )

    def get_department(self):
        return self.shop

    def delete(self):
        from src.forecast.models import OperationType
        super(WorkType, self).delete()
        operation_type = OperationType.objects.filter(work_type_id=self.pk).first()
        if operation_type:
            operation_type.delete()
        # self.dttm_deleted = datetime.datetime.now()
        # self.save()


class UserWeekdaySlot(AbstractModel):
    class Meta(object):
        verbose_name = 'Пользовательский слот'
        verbose_name_plural = 'Пользовательские слоты'

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.worker.last_name, self.slot.name, self.weekday, self.id)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    shop = models.ForeignKey(Shop, blank=True, null=True, on_delete=models.PROTECT)
    employment = models.ForeignKey(Employment, on_delete=models.PROTECT, null=True)
    slot = models.ForeignKey('Slot', on_delete=models.CASCADE)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    is_suitable = models.BooleanField(default=True)


class Slot(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Слот'
        verbose_name_plural = 'Слоты'

    def __str__(self):
        if self.work_type:
            work_type_name = self.work_type.name
        else:
            work_type_name = None
        return '{}, начало: {}, конец: {}, {}, {}, {}'.format(
            work_type_name,
            self.tm_start,
            self.tm_end,
            self.shop.name,
            self.shop.parent.name,
            self.id
        )

    id = models.BigAutoField(primary_key=True)

    name = models.CharField(max_length=128)

    tm_start = models.TimeField(default=datetime.time(hour=7))
    tm_end = models.TimeField(default=datetime.time(hour=23, minute=59, second=59))
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT) # todo delete this by cashbox_type
    work_type = models.ForeignKey(WorkType, null=True, blank=True, on_delete=models.PROTECT)
    workers_needed = models.IntegerField(default=1)

    worker = models.ManyToManyField(User, through=UserWeekdaySlot)

class EmploymentWorkType(AbstractModel):
    class Meta(object):
        verbose_name = 'Информация по сотруднику-типу работ'
        unique_together = (('employment', 'work_type'),)

    def __str__(self):
        return '{}, {}, {}'.format(self.employment.employee.user.last_name, self.work_type.work_type_name.name, self.id)

    id = models.BigAutoField(primary_key=True)

    # DO_NOTHING т.к. реально Employment мы удалять не будем, а только деактивируем проставив dttm_deleted
    # EmploymentWorkType без Employment вряд ли где-то используется,
    # поэтому в случае необходимости восстановить трудоустройство, восстановятся и типы работ
    employment = models.ForeignKey(Employment, on_delete=models.DO_NOTHING, related_name="work_types")
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)

    is_active = models.BooleanField(default=True)

    period = models.PositiveIntegerField(default=90)  # show for how long in days the data was collect

    mean_speed = models.FloatField(default=1)
    bills_amount = models.PositiveIntegerField(default=0)
    priority = models.IntegerField(default=0)

    # how many hours did he work
    duration = models.FloatField(default=0)

    def get_department(self):
        return self.employment.shop


class WorkerConstraint(AbstractModel):
    class Meta(object):
        verbose_name = 'Ограничения сотрудника'
        unique_together = (('employment', 'weekday', 'tm'),)

    def __str__(self):
        return '{} {}, {}, {}, {}'.format(self.employment.employee.user.last_name, self.employment.id, self.weekday, self.tm, self.id)

    id = models.BigAutoField(primary_key=True)
    shop = models.ForeignKey(Shop, blank=True, null=True, on_delete=models.PROTECT, related_name='worker_constraints')
    employment = models.ForeignKey(Employment, on_delete=models.PROTECT, related_name='worker_constraints')

    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    is_lite = models.BooleanField(default=False)  # True -- если сам сотрудник выставил, False -- если менеджер
    tm = models.TimeField()

    def get_department(self):
        return self.employment.shop


class WorkerDayQuerySet(AnnotateValueEqualityQSMixin, QuerySet):
    def get_plan_approved(self, *args, **kwargs):
        return self.filter(*args, is_fact=False, is_approved=True, **kwargs)

    def get_plan_not_approved(self, *args, **kwargs):
        return self.filter(*args, is_fact=False, is_approved=False, **kwargs)

    def get_fact_approved(self, *args, **kwargs):
        return self.filter(*args, is_fact=True, is_approved=True, **kwargs)

    def get_fact_not_approved(self, *args, **kwargs):
        return self.filter(*args, is_fact=True, is_approved=False, **kwargs)

    def get_plan_edit(self, *args, **kwargs):
        return self.get_last_ordered(
            *args,
            is_fact=False,
            order_by=[
                'is_approved',
                '-id',
            ],
            **kwargs
        )

    def get_last_ordered(self, *args, is_fact, order_by, **kwargs):
        ordered_subq = self.filter(
            dt=OuterRef('dt'),
            employee_id=OuterRef('employee_id'),
            is_fact=is_fact,
        ).order_by(*order_by).values_list('id')[:1]
        return self.filter(
            *args,
            is_fact=is_fact,
            id=Subquery(ordered_subq),
            **kwargs,
        )

    def get_fact_edit(self, **kwargs):
        raise NotImplementedError

    def get_tabel(self, *args, **kwargs):
        return self.annotate(
            has_fact_approved_on_dt=Exists(WorkerDay.objects.filter(
                employee_id=OuterRef('employee_id'),
                dt=OuterRef('dt'),
                is_fact=True,
                is_approved=True,
                type__is_dayoff=False,
                dttm_work_start__isnull=False, dttm_work_end__isnull=False,
                work_hours__gt=datetime.timedelta(0),
            ).exclude(
                type_id=WorkerDay.TYPE_EMPTY,
            ))
        ).filter(
            Q(
                is_fact=True, has_fact_approved_on_dt=True,
                dttm_work_start__isnull=False, dttm_work_end__isnull=False,
                work_hours__gt=datetime.timedelta(0),
            ) |
            Q(
                type__is_dayoff=True, is_fact=False, has_fact_approved_on_dt=False,
            ),
            is_approved=True,
            *args,
            **kwargs,
        )


class WorkerDayManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(employment_id__isnull=True, employee_id__isnull=False)

    def qos_current_version(self, approved_only=False):
        if approved_only:
            return super().get_queryset().filter(
                Q(child__id__isnull=True) | Q(child__worker_day_approve=False),
                worker_day_approve=True,
            )
        else:
            return super().get_queryset().filter(child__id__isnull=True)
        return super().get_queryset().filter(child__id__isnull=True)

    def qos_initial_version(self):
        return super().get_queryset().filter(parent_worker_day__isnull=True)

    def qos_filter_version(self, checkpoint, approved_only = False):
        """
        :param checkpoint: 0 or 1 / True of False. If 1 -- current version, else -- initial
        :return:
        """
        if checkpoint:
            return self.qos_current_version(approved_only)
        else:
            return self.qos_initial_version()

    def get_last_plan(self,  *args, **kwargs):
        """
        Возвращает плановый график - микс подтвержденного и неподтвержденного,
        последнюю версию за каждый день.
        """
        super().get_queryset()
        subq_kwargs = kwargs.copy()
        subq_kwargs.pop('dt', None)
        subq_kwargs.pop('employee_id', None)
        subq_kwargs.pop('is_fact', None)
        max_dt_subq = WorkerDay.objects.filter(
            dt=OuterRef('dt'),
            employee_id=OuterRef('employee_id'),
            is_fact=False,
            **subq_kwargs,
            # shop_id=OuterRef('shop_id')
        ).values( # for group by
            'dttm_modified'
        ).annotate(dt_max=Max('dttm_modified')).values('dt_max')[:1]
        return super().get_queryset().filter(
            *args,
            **kwargs,
            is_fact=False,
            dttm_modified=Subquery(max_dt_subq),
        )

    @staticmethod
    def qos_get_current_worker_day(worker_day):
        while True:
            current_worker_day = worker_day
            try:
                worker_day = worker_day.child
            except WorkerDay.child.RelatedObjectDoesNotExist:
                break
        return current_worker_day


class WorkerDayOutsourceNetwork(AbstractModel):
    workerday = models.ForeignKey('timetable.WorkerDay', on_delete=models.CASCADE)
    network = models.ForeignKey('base.Network', on_delete=models.CASCADE)


class WorkerDayType(AbstractModel):
    GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS = 'average_sawh_hours'
    GET_WORK_HOURS_METHOD_TYPE_NORM_HOURS = 'norm_hours'
    GET_WORK_HOURS_METHOD_TYPE_MANUAL = 'manual'

    GET_WORK_HOURS_METHOD_TYPES = (
        (GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS,
         'Расчет часов на основе среднемесячного значения рекомендуемой нормы'),
        (GET_WORK_HOURS_METHOD_TYPE_NORM_HOURS, 'Расчет часов на основе нормы по производственному календарю'),
        (GET_WORK_HOURS_METHOD_TYPE_MANUAL, 'Ручное проставление часов'),
    )

    code = models.CharField(max_length=64, primary_key=True, verbose_name='Код', help_text='Первычный ключ')
    name = models.CharField(max_length=64, verbose_name='Имя')
    short_name = models.CharField('Для отображения в ячейке', max_length=8)
    html_color = models.CharField(max_length=7)
    use_in_plan = models.BooleanField('Используем ли в плане')
    use_in_fact = models.BooleanField('Используем ли в факте')
    excel_load_code = models.CharField(
        'Текстовый код для загрузки и выгрузки в график/табель', max_length=8, unique=True)
    is_dayoff = models.BooleanField(
        'Нерабочий день',
        help_text='Если не нерабочий день, то '
                  'необходимо проставлять время и магазин и можно создавать несколько на 1 дату',
    )
    is_work_hours = models.BooleanField(
        'Считать ли в сумму рабочих часов',
        help_text='Если False, то не учитывается в сумме рабочих часов в статистике и не идет в белый табель',
        default=False,
    )
    is_reduce_norm = models.BooleanField('Снижает ли норму часов (отпуска, больничные и тд)', default=False)
    is_system = models.BooleanField('Системный (нельзя удалять)', default=False, editable=False)
    show_stat_in_days = models.BooleanField(
        'Отображать в статистике по сотрудникам количество дней отдельно для этого типа',
        default=False,
    )
    show_stat_in_hours = models.BooleanField(
        'Отображать в статистике по сотрудникам сумму часов отдельно для этого типа',
        default=False,
    )
    get_work_hours_method = models.CharField(
        'Способ получения рабочих часов',
        help_text='Актуально для нерабочих типов дней. '
                  'Для рабочих типов кол-во часов считается на основе времени начала и окончания.',
        max_length=32, blank=True,
        choices=GET_WORK_HOURS_METHOD_TYPES,
    )
    has_details = models.BooleanField('Есть детали рабочего дня', default=False)
    allowed_additional_types = models.ManyToManyField(
        'self', blank=True,
        verbose_name='Типы дней, которые можно добавлять одновременно с текущим типом дня (только для нерабочих типов дней)',
        help_text='Например, если необходимо разрешить создание рабочих дней в отпуск, то '
                  'для типа дня "Отпуск" нужно добавить в это поле тип дня "Рабочий день',
        symmetrical=False,
        related_name='allowed_as_additional_for',
    )
    ordering = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    tracker = FieldTracker(fields=('is_reduce_norm',))

    class Meta(AbstractModel.Meta):
        ordering = ['-ordering', 'name']
        verbose_name = 'Тип дня сотрудника'
        verbose_name_plural = 'Типы дней сотрудников'

    def __str__(self):
        return '{} ({})'.format(self.name, self.code)

    @classmethod
    def get_is_dayoff_types(cls):
        return set(cls.objects.filter(is_dayoff=True).values_list('code', flat=True))

    @classmethod
    def get_wd_types_dict(cls):
        return {wdt.code: wdt for wdt in cls.objects.prefetch_related('allowed_additional_types', 'allowed_as_additional_for')}

    @tracker
    def save(self, *args, **kwargs):
        if self.code and self.tracker.has_changed('is_reduce_norm'):
            cache.delete_pattern("prod_cal_*_*_*")
        return super().save(*args, **kwargs)


class Restriction(AbstractModel):
    RESTRICTION_TYPE_DT_MAX_HOURS = 1

    RESTRICTION_TYPE_CHOICES = (
        (RESTRICTION_TYPE_DT_MAX_HOURS, 'Максимальное количество часов на одну дату у сотрудника'),
    )

    position = models.ForeignKey('base.WorkerPosition', null=True, blank=True, on_delete=models.CASCADE)
    worker_day_type = models.ForeignKey('timetable.WorkerDayType', null=True, blank=True, on_delete=models.CASCADE)
    dt_max_hours = models.DurationField(null=True, blank=True)
    restriction_type = PositiveSmallIntegerField(
        choices=RESTRICTION_TYPE_CHOICES, default=RESTRICTION_TYPE_DT_MAX_HOURS)
    is_vacancy = models.BooleanField(null=None, blank=True, default=None,
                                         verbose_name='None -- для любой смены (осн. или доп.), '
                                                      'True -- только для доп. смен, False -- только для осн. смен')

    class Meta:
        verbose_name = 'Ограничение'
        verbose_name_plural = 'Ограничения'

    @classmethod
    def check_restrictions(cls, employee_days_q, is_fact, exc_cls=None):  # TODO: тест
        restrictions = cls.objects.annotate(
            dt_max_hours_restrictions=ArraySubquery(WorkerDay.objects.filter(
                employee_days_q,
                is_fact=is_fact,
                is_approved=True,
                # employment__position=OuterRef('position'),  # TODO: джоин если None ???
                type=OuterRef('worker_day_type'),
            ).values_list(
                'employee',
                'dt',
            ).annotate(
                current_work_hours=Sum('work_hours'),
            ).filter(
                current_work_hours__gt=OuterRef('dt_max_hours'),
            ).annotate(
                data_json=Func(
                    Value('employee', output_field=CharField()), F("employee"),
                    Value('dt', output_field=CharField()), F("dt"),
                    function="jsonb_build_object",
                    output_field=JSONField()
                ),
            ).values_list(
                'data_json', flat=True,
            ).distinct()),
        ).values(
            'dt_max_hours_restrictions',
        )
        for restriction in restrictions:
            if restriction['dt_max_hours_restrictions']:
                raise exc_cls(
                    restriction['dt_max_hours_restrictions']  # TODO: человекочитаемая ошибка
                )


class WorkerDay(AbstractModel):
    """
    Ключевая сущность, которая определяет, что делает сотрудник в определенный момент времени (работает, на выходном и тд)

    Что именно делает сотрудник в выбранный день определяет поле type. При этом, если сотрудник работает в этот день, то
    у него должен быть указан магазин (shop). Во всех остальных случаях shop_id должно быть пустым (aa: fixme WorkerDaySerializer)

    """
    class Meta:
        verbose_name = 'Рабочий день сотрудника'
        verbose_name_plural = 'Рабочие дни сотрудников'
        unique_together = (
            ('code', 'is_approved'),
        )

    TYPE_HOLIDAY = 'H'
    TYPE_WORKDAY = 'W'
    TYPE_VACATION = 'V'
    TYPE_SICK = 'S'
    TYPE_QUALIFICATION = 'Q'
    TYPE_ABSENSE = 'A'
    TYPE_MATERNITY = 'M'
    TYPE_BUSINESS_TRIP = 'T'
    TYPE_ETC = 'O'
    TYPE_EMPTY = 'E'
    TYPE_SELF_VACATION = 'TV'  # TV, а не SV, потому что так написали в документации

    TYPES = [
        (TYPE_HOLIDAY, 'Выходной'),
        (TYPE_WORKDAY, 'Рабочий день'),
        (TYPE_VACATION, 'Отпуск'),
        (TYPE_SICK, 'Больничный лист'),
        (TYPE_QUALIFICATION, 'Квалификация'),
        (TYPE_ABSENSE, 'Неявка до выяснения обстоятельств'),
        (TYPE_MATERNITY, 'Б/л по беременноси и родам'),
        (TYPE_BUSINESS_TRIP, 'Командировка'),
        (TYPE_ETC, 'Другое'),
        (TYPE_EMPTY, 'Пусто'),
        (TYPE_SELF_VACATION, 'Отпуск за свой счёт'),
    ]

    TYPES_USED = [
        TYPE_HOLIDAY,
        TYPE_WORKDAY,
        TYPE_VACATION,
        TYPE_SELF_VACATION,
        TYPE_SICK,
        TYPE_QUALIFICATION,
        TYPE_ABSENSE,
        TYPE_MATERNITY,
        TYPE_BUSINESS_TRIP,
        TYPE_ETC,
        TYPE_EMPTY,
    ]

    SOURCE_FAST_EDITOR = 0
    SOURCE_FULL_EDITOR = 1
    SOURCE_DUPLICATE = 2
    SOURCE_ALGO = 3
    SOURCE_AUTO_CREATED_VACANCY = 4
    SOURCE_CHANGE_RANGE = 5
    SOURCE_COPY_RANGE = 6
    SOURCE_EXCHANGE = 7
    SOURCE_EXCHANGE_APPROVED = 8
    SOURCE_UPLOAD = 9
    SOURCE_CHANGE_LIST = 10
    SOURCE_SHIFT_ELONGATION = 11
    SOURCE_ON_CANCEL_VACANCY = 12
    SOURCE_ON_CONFIRM_VACANCY = 13
    SOURCE_INTEGRATION = 14
    SOURCE_ON_APPROVE = 15
    SOURCE_EDITABLE_VACANCY = 16
    SOURCE_COPY_APPROVED_PLAN_TO_PLAN = 17
    SOURCE_COPY_APPROVED_PLAN_TO_FACT = 18
    SOURCE_COPY_APPROVED_FACT_TO_FACT = 19
    SOURCE_AUTO_FACT = 20
    RECALC_FACT_FROM_ATT_RECORDS = 21

    SOURCES = [
        (SOURCE_FAST_EDITOR, 'Создание рабочего дня через быстрый редактор'),
        (SOURCE_FULL_EDITOR, 'Создание рабочего дня через полный редактор'),
        (SOURCE_DUPLICATE, 'Создание через копирование в графике (ctrl-c + ctrl-v)'),
        (SOURCE_ALGO, 'Автоматическое создание алгоритмом'),
        (SOURCE_AUTO_CREATED_VACANCY, 'Автоматическое создание биржей смен'),
        (SOURCE_CHANGE_RANGE, 'Создание смен через change_range (Обычно используется для получения отпусков/больничных из 1С ЗУП)'),
        (SOURCE_COPY_RANGE, 'Создание смен через copy_range (Копирование по датам)'),
        (SOURCE_EXCHANGE, 'Создание смен через exchange (Обмен сменами)'),
        (SOURCE_EXCHANGE_APPROVED, 'Создание смен через exchange_approved (Обмен сменами в подтвержденной версии)'),
        (SOURCE_UPLOAD, 'Создание смен через загрузку графика'),
        (SOURCE_CHANGE_LIST, 'Создание смен через change_list (Проставление типов дней на промежуток для сотрудника)'),
        (SOURCE_SHIFT_ELONGATION, 'Автоматическое создание смен через shift_elongation (Расширение смен)'),
        (SOURCE_ON_CANCEL_VACANCY, 'Автоматическое создание смен при отмене вакансии'),
        (SOURCE_ON_CONFIRM_VACANCY, 'Автоматическое создание смен при принятии вакансии'),
        (SOURCE_INTEGRATION, 'Создание смен через интеграцию'),
        (SOURCE_ON_APPROVE, 'Создание смен при подтверждении графика'),
        (SOURCE_EDITABLE_VACANCY, 'Создание смен при получении редактируемой вакансии'),
        (SOURCE_COPY_APPROVED_PLAN_TO_PLAN, 'Создание смен через copy_approved (Копирование из плана в план)'),
        (SOURCE_COPY_APPROVED_PLAN_TO_FACT, 'Создание смен через copy_approved (Копирование из плана в факт)'),
        (SOURCE_COPY_APPROVED_FACT_TO_FACT, 'Создание смен через copy_approved (Копирование из факта в факт)'),
        (SOURCE_AUTO_FACT, 'Создание смен во время отметок'),
        (RECALC_FACT_FROM_ATT_RECORDS, 'Пересчет факта на основе отметок'),
    ]

    def __str__(self):
        return '{}, {}, {}, {}, {}, {}, {}, {}'.format(
            self.employee.user.last_name if (self.employee and self.employee.user_id) else 'No worker',
            self.shop.name if self.shop else '',
            self.shop.parent.name if self.shop and self.shop.parent else '',
            self.dt,
            self.type,
            'Fact' if self.is_fact else 'Plan',
            'Approved' if self.is_approved else 'Not approved',
            self.id
        )

    def __repr__(self):
        return self.__str__()

    @classmethod
    def _get_batch_create_extra_kwargs(cls):
        return {
            'need_count_wh': True,
        }

    @classmethod
    def _get_rel_objs_mapping(cls):
        # TODO: добавить условие, только при выполнении которого, действия над связанными объектами выполняются, например
        #    детали рабочего дня только если тип "РД"
        #    аутсорс только если план и is_vacancy=True и is_outsource=True
        return {
            'worker_day_details': (WorkerDayCashboxDetails, 'worker_day_id'),
            'outsources': (WorkerDayOutsourceNetwork, 'workerday_id'),
        }

    @classmethod
    def _get_batch_update_select_related_fields(cls):
        return ['employee__user__network', 'shop__network', 'type']

    @classmethod
    def _get_batch_delete_scope_fields_list(cls):
        return ['dt', 'employee_id', 'is_fact', 'is_approved']

    @classmethod
    def _enrich_perms_data(cls, action, perms_data, obj_dict):
        graph_type = WorkerDayPermission.FACT if obj_dict.get('is_fact') else WorkerDayPermission.PLAN
        wd_type_id = obj_dict.get('type_id') or obj_dict.get('type').code
        dt = obj_dict.get('dt')
        shop_id = obj_dict.get('shop_id')
        employee_id = obj_dict.get('employee_id')
        is_vacancy = obj_dict.get('is_vacancy', False)
        k = f'{graph_type}_{action}_{wd_type_id}_{shop_id}_{employee_id}_{is_vacancy}'
        perms_data.setdefault(k, set()).add(dt)

    @classmethod
    def _get_check_perms_extra_kwargs(cls, user=None):
        kwargs = {
            'wd_types_dict': WorkerDayType.get_wd_types_dict(),
        }
        if user:
            kwargs['cached_data'] = {
                'user_shops': list(user.get_shops(include_descendants=True).values_list('id', flat=True)),
                'user_subordinated_group_ids': list(Group.get_subordinated_group_ids(user)),
            }
        return kwargs

    @classmethod
    def _check_delete_qs_perm(cls, user, delete_qs, **kwargs):
        from src.timetable.worker_day_permissions.checkers import DeleteQsWdPermissionChecker
        perm_checker = DeleteQsWdPermissionChecker(
            user=user,
            wd_qs=delete_qs,
            cached_data={
                'wd_types_dict': kwargs.get('wd_types_dict'),
            },
        )
        if not perm_checker.has_permission():
            raise PermissionDenied(perm_checker.err_message)

    @classmethod
    def _get_diff_lookup_fields(cls):
        return [
            'dt',
            'employee_id',
            'shop_id',
            'type_id',
            'is_fact',
            'is_vacancy',
        ]

    @classmethod
    def _get_grouped_perm_check_data(self, diff_data):
        """
        :param diff_data: список кортежей с данным полей из _get_diff_lookup_fields (важен порядок)
        :return: данные для проверка по мин. и по макс. дате (
            например, если создается выходной на месяц, то проверка пойдет для первого и последнего дня месяца).
        """
        grouped_wd_min_max_dt_data = {}
        grouped_wd_perm_check_data = []
        for dt, employee_id, shop_id, type_id, is_fact, is_vacancy in diff_data:
            k_data = dict(
                employee_id=employee_id,
                type_id=type_id,
                shop_id=shop_id,
                is_fact=is_fact,
                is_vacancy=is_vacancy,
            )
            k = json.dumps(k_data, sort_keys=True, cls=DjangoJSONEncoder)
            min_max_dt_data = grouped_wd_min_max_dt_data.setdefault(k, {})
            min_max_dt_data['min_dt'] = min(min_max_dt_data.get('min_dt', dt), dt)
            min_max_dt_data['max_dt'] = max(min_max_dt_data.get('max_dt', dt), dt)
        for k, min_max_dt_data in grouped_wd_min_max_dt_data.items():
            wd_data = json.loads(k)
            if min_max_dt_data.get('min_dt') == min_max_dt_data.get('max_dt'):
                single_wd_data = wd_data.copy()
                single_wd_data['dt'] = min_max_dt_data.get('min_dt')
                grouped_wd_perm_check_data.append(single_wd_data)
            else:
                min_wd_data = wd_data.copy()
                min_wd_data['dt'] = min_max_dt_data.get('min_dt')
                grouped_wd_perm_check_data.append(min_wd_data)
                max_wd_data = wd_data.copy()
                max_wd_data['dt'] = min_max_dt_data.get('max_dt')
                grouped_wd_perm_check_data.append(max_wd_data)
        return grouped_wd_perm_check_data

    @classmethod
    def _pre_batch(cls, user, **kwargs):
        if kwargs.get('model_options', {}).get('delete_not_allowed_additional_types'):
            cls._delete_not_allowed_additional_types(**kwargs)
        check_perms_extra_kwargs = kwargs.get('check_perms_extra_kwargs', {})
        grouped_checks = check_perms_extra_kwargs.pop('grouped_checks', False)
        if grouped_checks:
            diff_data = kwargs.get('diff_data')
            if diff_data:
                check_active_empl = check_perms_extra_kwargs.pop('check_active_empl', True)
                created = diff_data.get('created')
                if created:
                    grouped_wd_perm_check_data = cls._get_grouped_perm_check_data(created)
                    for wd_data in grouped_wd_perm_check_data:
                        cls._check_create_single_obj_perm(user, wd_data, check_active_empl=check_active_empl)
                deleted = diff_data.get('deleted')
                if deleted:
                    grouped_wd_perm_check_data = cls._get_grouped_perm_check_data(deleted)
                    for wd_data in grouped_wd_perm_check_data:
                        cls._check_delete_single_wd_data_perm(user, wd_data)

    @classmethod
    def _delete_not_allowed_additional_types(cls, **kwargs):
        grouped_by_type = {}
        for obj in kwargs.get('created_objs', []):
            grouped_by_type.setdefault(obj.type_id, []).append(obj)

        allowed_wd_types_dict = {}
        for from_workerdaytype_id, to_workerdaytype_id in WorkerDayType.allowed_additional_types.through.objects.filter(
            from_workerdaytype_id__in=list(grouped_by_type.keys())
        ).values_list(
            'from_workerdaytype_id',
            'to_workerdaytype_id',
        ):
            allowed_wd_types_dict.setdefault(from_workerdaytype_id, []).append(to_workerdaytype_id)

        delete_not_allowed_additional_types_q = Q()
        for wd_type_id, objects in grouped_by_type.items():
            for obj in objects:
                delete_not_allowed_additional_types_q |= Q(
                    ~Q(type_id=obj.type_id),
                    ~Q(type__in=allowed_wd_types_dict.get(wd_type_id, [])),
                    employee_id=obj.employee_id,
                    is_fact=obj.is_fact,
                    is_approved=obj.is_approved,
                    dt=obj.dt,
                )
        if delete_not_allowed_additional_types_q:
            delete_qs = WorkerDay.objects.filter(delete_not_allowed_additional_types_q)
            objs_to_delete = list(delete_qs)
            _total_deleted_count, deleted_dict = delete_qs.delete()
            stats = kwargs.setdefault('stats', {})
            if 'deleted_objs' in kwargs:
                kwargs['deleted_objs'].extend(objs_to_delete)
            if 'diff_data' in kwargs and 'diff_obj_keys' in kwargs:
                for obj_to_delete in objs_to_delete:
                    kwargs['diff_data'].setdefault('deleted', []).append(
                        tuple(obj_deep_get(obj_to_delete, *keys) for keys in kwargs['diff_obj_keys']))
            for original_deleted_cls_name, deleted_count in deleted_dict.items():
                if deleted_count:
                    deleted_cls_name = original_deleted_cls_name.split('.')[1]
                    deleted_cls_stats = stats.setdefault(deleted_cls_name, {})
                    deleted_cls_stats['deleted'] = deleted_cls_stats.get('deleted', 0) + deleted_dict.get(
                        original_deleted_cls_name)

    @classmethod
    def _approve_delete_scope_filters_wdays(cls, **kwargs):
        from src.timetable.worker_day.utils.approve import WorkerDayApproveHelper
        from src.timetable.worker_day.serializers import WorkerDayApproveSerializer
        delete_scope_filters = kwargs.get('delete_scope_filters', {})
        employee_ids = []
        if 'employee__tabel_code' in delete_scope_filters:
            employee_ids = list(Employee.objects.filter(
                tabel_code=delete_scope_filters.get('employee__tabel_code')).values_list('id', flat=True))
        elif 'employee__tabel_code__in' in delete_scope_filters:
            employee_ids = list(Employee.objects.filter(
                tabel_code__in=delete_scope_filters.get('employee__tabel_code__in')).values_list('id', flat=True))
        if employee_ids:
            data = dict(
                employee_ids=employee_ids,
                is_fact=delete_scope_filters.get('is_fact'),
                dt_from=delete_scope_filters.get('dt__gte'),
                dt_to=delete_scope_filters.get('dt__lte'),
                wd_types=delete_scope_filters.get('type_id__in'),
            )
            serializer = WorkerDayApproveSerializer(data=data)
            serializer.is_valid(raise_exception=True)
            exclude_approve_q = Q()
            grouped_by_type = {}
            for obj in kwargs.get('created_objs', []):
                grouped_by_type.setdefault(obj.type_id, []).append(obj.dt)
            for obj in kwargs.get('deleted_objs', []):
                grouped_by_type.setdefault(obj.type_id, []).append(obj.dt)
            allowed_wd_types_dict = {}
            for from_workerdaytype_id, to_workerdaytype_id in WorkerDayType.allowed_additional_types.through.objects.filter(
                    from_workerdaytype_id__in=list(grouped_by_type.keys())
            ).values_list(
                'from_workerdaytype_id',
                'to_workerdaytype_id',
            ):
                allowed_wd_types_dict.setdefault(from_workerdaytype_id, []).append(to_workerdaytype_id)
            for wd_type_id, dates in grouped_by_type.items():
                exclude_approve_q |= Q(
                    type__in=allowed_wd_types_dict.get(wd_type_id, []),
                    dt__in=dates,
                )
            WorkerDayApproveHelper(
                user=kwargs.get('user'),
                any_draft_wd_exists=False,
                exclude_approve_q=exclude_approve_q,
                **serializer.validated_data,
            ).run()

    @classmethod
    def _post_batch(cls, **kwargs):
        if kwargs.get('model_options', {}).get('approve_delete_scope_filters_wdays'):
            cls._approve_delete_scope_filters_wdays(**kwargs)
        cls._invalidate_cache(**kwargs)

    @classmethod
    def _invalidate_cache(cls, **kwargs):
        reduce_norm_types = set(WorkerDayType.objects.filter(is_reduce_norm=True).values_list('code', flat=True))
        grouped_by_employee = {}
        for obj in kwargs.get('created_objs', []):
            grouped_by_employee.setdefault(obj.employee_id, []).append(obj.type_id)
        for obj in kwargs.get('deleted_objs', []):
            grouped_by_employee.setdefault(obj.employee_id, []).append(obj.type_id)
        for i, obj in enumerate(kwargs.get('updated_objs', [])):
            prev_type = kwargs['diff_data']['before_update'][i][3]
            new_type = obj.type_id
            if prev_type != new_type or new_type in reduce_norm_types:
                grouped_by_employee.setdefault(obj.employee_id, []).extend([new_type, prev_type])

        for employee_id, types in grouped_by_employee.items():
            if set(types).intersection(reduce_norm_types):
                transaction.on_commit(lambda empl_id=employee_id: cache.delete_pattern(f"prod_cal_*_*_{empl_id}"))

    @classmethod
    def _check_create_single_obj_perm(cls, user, obj_data, check_active_empl=True, **extra_kwargs):
        from src.timetable.worker_day_permissions.checkers import CreateSingleWdPermissionChecker
        perm_checker = CreateSingleWdPermissionChecker(user=user, wd_data=obj_data, check_active_empl=check_active_empl)
        if not perm_checker.has_permission():
            raise PermissionDenied(perm_checker.err_message)

    @classmethod
    def _check_update_single_obj_perm(cls, user, existing_obj, obj_data, check_active_empl=True, **extra_kwargs):
        from src.timetable.worker_day_permissions.checkers import (
            UpdateSingleWdPermissionChecker, CreateSingleWdPermissionChecker, DeleteSingleWdPermissionChecker
        )
        if existing_obj.type != obj_data['type'] or existing_obj.shop_id != obj_data['shop_id'] \
                or existing_obj.dt != obj_data['dt']:
            # TODO: тест
            perm_checker = DeleteSingleWdPermissionChecker(user=user, wd_obj=existing_obj)
            if not perm_checker.has_permission():
                raise PermissionDenied(perm_checker.err_message)
            perm_checker = CreateSingleWdPermissionChecker(user=user, wd_data=obj_data, check_active_empl=check_active_empl)
            if not perm_checker.has_permission():
                raise PermissionDenied(perm_checker.err_message)
        else:
            perm_checker = UpdateSingleWdPermissionChecker(user=user, wd_data=obj_data, check_active_empl=check_active_empl)
            if not perm_checker.has_permission():
                raise PermissionDenied(perm_checker.err_message)

    @classmethod
    def _check_delete_single_obj_perm(cls, user, existing_obj=None, obj_id=None, check_active_empl=False, **extra_kwargs):
        from src.timetable.worker_day_permissions.checkers import DeleteSingleWdPermissionChecker
        perm_checker = DeleteSingleWdPermissionChecker(user=user, wd_obj=existing_obj, wd_id=obj_id)
        if not perm_checker.has_permission():
            raise PermissionDenied(perm_checker.err_message)

    @classmethod
    def _check_delete_single_wd_data_perm(cls, user, obj_data, check_active_empl=False, **extra_kwargs):
        from src.timetable.worker_day_permissions.checkers import DeleteSingleWdDataPermissionChecker
        perm_checker = DeleteSingleWdDataPermissionChecker(
            user=user, wd_data=obj_data, check_active_empl=check_active_empl)
        if not perm_checker.has_permission():
            raise PermissionDenied(perm_checker.err_message)

    @classmethod
    def _get_batch_update_or_create_transaction_checks_kwargs(cls, **kwargs):
        return {
            'employee_days_q': kwargs.get('q_for_delete'),
            'user': kwargs.get('user'),
        }

    @classmethod
    def _run_batch_update_or_create_transaction_checks(cls, *args, **kwargs):
        cls.check_work_time_overlap(employee_days_q=kwargs.get('employee_days_q'), exc_cls=ValidationError)
        cls.check_multiple_workday_types(employee_days_q=kwargs.get('employee_days_q'), exc_cls=ValidationError)
        user = kwargs.get('user')
        if user and user.network_id and not user.network.allow_creation_several_wdays_for_one_employee_for_one_date:
            cls.check_only_one_wday_on_date(employee_days_q=kwargs.get('employee_days_q'), exc_cls=ValidationError)

    @classmethod
    def _batch_update_extra_handler(cls, obj):
        obj.dttm_work_start_tabel, obj.dttm_work_end_tabel, obj.work_hours = obj._calc_wh()
        obj.work_hours = obj._round_wh()
        return {
            'dttm_work_start_tabel',
            'dttm_work_end_tabel',
            'work_hours',
        }

    @classmethod
    def _has_group_permissions(
            cls, user, employee_id, dt, user_shops=None, get_subordinated_group_ids=None, is_vacancy=False, shop_id=None, action=None, graph_type=None):
        if not employee_id:
            return True

        check_is_vacancy_perm_cond = (
            (not action and not graph_type) or
            (graph_type == WorkerDayPermission.PLAN and action in [
                WorkerDayPermission.UPDATE, WorkerDayPermission.DELETE]) or
            (graph_type == WorkerDayPermission.FACT)
        )
        if is_vacancy and check_is_vacancy_perm_cond:
            if not user_shops:
                user_shops = user.get_shops(include_descendants=True).values_list('id', flat=True)
            if isinstance(shop_id, str):
                shop_id = int(shop_id)
            if shop_id in user_shops:
                return True
        employee = user.get_subordinates(
            dt=dt,
            user_shops=user_shops,
            user_subordinated_group_ids=get_subordinated_group_ids,
        ).filter(id=employee_id).first()
        if not employee:
            active_empls = Employment.objects.get_active(
                dt_from=dt,
                dt_to=dt,
                employee_id=employee_id,
            )
            if active_empls.exists():
                return False
            else:
                raise ValidationError(
                    _("Can't create a working day in the schedule, since the user is not employed during this period"))
        return True

    @classmethod
    def _get_skip_update_equality_fields(cls, existing_obj):
        skip_fields_list = ['created_by', 'last_edited_by', 'source']
        if not (existing_obj.type.is_dayoff and existing_obj.type.is_work_hours and
                existing_obj.type.get_work_hours_method == WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL):
            # TODO: тест
            skip_fields_list.append('work_hours')
        return skip_fields_list

    def calc_day_and_night_work_hours(self, work_hours=None, work_start=None, work_end=None):
        from src.util.models_converter import Converter
        # TODO: нужно учитывать работу в праздничные дни? -- сейчас is_celebration в ProductionDay всегда False

        if self.type.is_dayoff:
            return 0.0, 0.0, 0.0

        work_hours = (work_hours or self.work_hours)
        if work_hours > datetime.timedelta(0):
            work_seconds = work_hours.seconds
        else:
            return 0.0, 0.0, 0.0

        work_start = work_start or self.dttm_work_start_tabel or self.dttm_work_start
        work_end = work_end or self.dttm_work_end_tabel or self.dttm_work_end
        if not (work_start and work_end):
            return 0.0, 0.0, 0.0

        work_hours = round(work_seconds / 3600, 2)

        night_edges = [Converter.parse_time(t) for t in Network.DEFAULT_NIGHT_EDGES]
        if self.shop and self.shop.network:
            night_edges = self.shop.network.night_edges_tm_list

        if work_end.time() <= night_edges[0] and work_start.date() == work_end.date():
            work_hours_day = work_hours
            return work_hours, work_hours_day, 0.0
        if work_start.time() >= night_edges[0] and work_end.time() <= night_edges[1]:
            work_hours_night = work_hours
            return work_hours, 0.0, work_hours_night

        network = self.shop.network if self.shop_id else None
        round_wh_alg_func = None
        if network and network.round_work_hours_alg is not None:
            round_wh_alg_func = Network.ROUND_WH_ALGS.get(network.round_work_hours_alg)

        if work_start.time() > night_edges[0] or work_start.time() < night_edges[1]:
            tm_start = _time_to_float(work_start.time())
        else:
            tm_start = _time_to_float(night_edges[0])
        if work_end.time() > night_edges[0] or work_end.time() < night_edges[1]:
            tm_end = _time_to_float(work_end.time())
        else:
            tm_end = _time_to_float(night_edges[1])

        night_seconds = (tm_end - tm_start if tm_end > tm_start else 24 - (tm_start - tm_end)) * 60 * 60

        if round_wh_alg_func:
            night_seconds = round_wh_alg_func(night_seconds / 3600) * 3600

        break_time_seconds = self._calc_break(self._get_breaks(), work_start, work_end, plan_approved=self.closest_plan_approved) * 60

        total_seconds = (work_seconds + break_time_seconds)

        break_time_subtractor_alias = None
        if network:
            break_time_subtractor_alias = network.settings_values_prop.get('break_time_subtractor')
        break_time_subtractor_cls = break_time_subtractor_map.get(break_time_subtractor_alias or 'default')
        break_time_subtractor = break_time_subtractor_cls(break_time_seconds, total_seconds, night_seconds)
        work_hours_day, work_hours_night = break_time_subtractor.calc()
        work_hours = work_hours_day + work_hours_night
        return work_hours, work_hours_day, work_hours_night

    def _get_breaks(self):
        position_break_triplet_cond = self.employment and self.employment.position and self.employment.position.breaks
        if self.shop and (self.shop.settings or position_break_triplet_cond or self.shop.network.breaks):
            return self.employment.position.breaks.breaks if position_break_triplet_cond else self.shop.settings.breaks.breaks if self.shop.settings else self.shop.network.breaks.breaks

    def _calc_break(self, breaks, dttm_work_start, dttm_work_end, plan_approved=None):
        work_hours = ((dttm_work_end - dttm_work_start).total_seconds() / 60)
        break_time = 0
        if not breaks:
            return break_time
        for break_triplet in breaks:
            if work_hours >= break_triplet[0] and work_hours <= break_triplet[1]:
                break_time = sum(break_triplet[2])
                break
        if plan_approved:
            # учитываем перерыв плана, если факт получился больше
            fact_hours = self.count_work_hours(dttm_work_start, dttm_work_end, break_time)
            plan_hours = plan_approved.work_hours
            if fact_hours > plan_hours:
                break_time = self._calc_break(breaks, plan_approved.dttm_work_start, plan_approved.dttm_work_end)
        return break_time

    def _calc_wh(self):
        from src.util.models_converter import Converter
        self.dt = Converter.parse_date(self.dt) if isinstance(self.dt, str) else self.dt
        breaks = self._get_breaks()
        if not self.type.is_dayoff and self.dttm_work_end and self.dttm_work_start and not breaks is None:
            dttm_work_start = _dttm_work_start = self.dttm_work_start
            dttm_work_end = _dttm_work_end = self.dttm_work_end
            if self.shop.network.crop_work_hours_by_shop_schedule and self.crop_work_hours_by_shop_schedule:
                shop_schedule = self.shop.get_schedule(dt=self.dt)
                if shop_schedule is None:
                    return dttm_work_start, dttm_work_end, datetime.timedelta(0)

                open_at_0 = all(getattr(shop_schedule['tm_open'], a) == 0 for a in ['hour', 'second', 'minute'])
                close_at_0 = all(getattr(shop_schedule['tm_close'], a) == 0 for a in ['hour', 'second', 'minute'])
                shop_24h_open = open_at_0 and close_at_0

                if not shop_24h_open:
                    dttm_shop_open = datetime.datetime.combine(self.dt, shop_schedule['tm_open'])
                    if self.dttm_work_start < dttm_shop_open:
                        dttm_work_start = dttm_shop_open

                    dttm_shop_close = datetime.datetime.combine(
                        (self.dt + datetime.timedelta(days=1)) if close_at_0 else self.dt, shop_schedule['tm_close'])
                    if self.dttm_work_end > dttm_shop_close:
                        dttm_work_end = dttm_shop_close
            break_time = None
            arrive_fine, departure_fine = 0, 0
            if self.is_fact:
                plan_approved = None
                if self.closest_plan_approved_id:
                    plan_approved = WorkerDay.objects.filter(id=self.closest_plan_approved_id).first()
                if plan_approved:
                    arrive_fine, departure_fine = self.get_fines(
                        _dttm_work_start,
                        _dttm_work_end,
                        plan_approved.dttm_work_start,
                        plan_approved.dttm_work_end,
                        self.employment.position.wp_fines if self.employment and self.employment.position else None,
                        self.shop.network,
                    )
                if self.shop.network.only_fact_hours_that_in_approved_plan and not self.type.is_dayoff:
                    if plan_approved:
                        late_arrival_delta = self.shop.network.allowed_interval_for_late_arrival
                        allowed_late_arrival_cond = late_arrival_delta and \
                            dttm_work_start > plan_approved.dttm_work_start and \
                            (dttm_work_start - plan_approved.dttm_work_start).total_seconds() < \
                                                                late_arrival_delta.total_seconds()
                        if allowed_late_arrival_cond:
                            dttm_work_start = plan_approved.dttm_work_start
                        else:
                            dttm_work_start = max(dttm_work_start, plan_approved.dttm_work_start)

                        early_departure_delta = self.shop.network.allowed_interval_for_early_departure
                        allowed_early_departure_cond = early_departure_delta and \
                                                    dttm_work_end < plan_approved.dttm_work_end and \
                                                    (plan_approved.dttm_work_end - dttm_work_end).total_seconds() < \
                                                    early_departure_delta.total_seconds()
                        if allowed_early_departure_cond:
                            dttm_work_end = plan_approved.dttm_work_end
                        else:
                            dttm_work_end = min(dttm_work_end, plan_approved.dttm_work_end)
                        break_time = self._calc_break(breaks, dttm_work_start, dttm_work_end, plan_approved=plan_approved)
                    else:
                        return dttm_work_start, dttm_work_end, datetime.timedelta(0)

            if break_time is None:
                break_time = self._calc_break(breaks, dttm_work_start, dttm_work_end)

            dttm_work_start, dttm_work_end = dttm_work_start + datetime.timedelta(minutes=arrive_fine), dttm_work_end - datetime.timedelta(minutes=departure_fine)

            return dttm_work_start, dttm_work_end, self.count_work_hours(dttm_work_start, dttm_work_end, break_time)

        # потенциально только для is_dayoff == true ? -- чтобы было наглядней сколько часов вычитается из нормы?
        # + вычитать из нормы из work_hours в типах is_reduce_norm?
        if self.type.is_dayoff and self.type.is_work_hours:
            work_hours = 0
            if self.type.get_work_hours_method == WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MONTH_AVERAGE_SAWH_HOURS:
                from src.timetable.worker_day.stat import WorkersStatsGetter
                employee_stats = WorkersStatsGetter(
                    employee_id=self.employee_id,
                    dt_from=self.dt,
                    dt_to=self.dt,
                    shop_id=self.employment.shop_id,
                ).run()
                work_hours = employee_stats.get(
                    self.employee_id, {}
                ).get(
                    'employments', {}
                ).get(
                    self.employment_id, {}
                ).get(
                    'one_day_value', {}
                ).get(
                    self.dt.month, 0
                )
            elif self.type.get_work_hours_method == WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_NORM_HOURS:
                prod_cal = ProdCal.objects.filter(
                    employee_id=self.employee_id,
                    dt=self.dt,
                    shop_id=self.employment.shop_id,
                ).first()
                if prod_cal:
                    work_hours = prod_cal.norm_hours

            elif self.type.get_work_hours_method == WorkerDayType.GET_WORK_HOURS_METHOD_TYPE_MANUAL:
                return None, None, self.work_hours

            return None, None, datetime.timedelta(hours=work_hours)

        return self.dttm_work_start, self.dttm_work_end, datetime.timedelta(0)

    def _round_wh(self):
        if self.work_hours > datetime.timedelta(0):
            network = None
            if self.shop_id and self.shop.network_id:
                network = self.shop.network
            elif self.employee_id and self.employee.user.network_id:
                network = self.employee.user.network

            if network and network.round_work_hours_alg is not None:
                round_wh_alg_func = Network.ROUND_WH_ALGS.get(network.round_work_hours_alg)
                self.work_hours = datetime.timedelta(hours=round_wh_alg_func(self.work_hours.total_seconds() / 3600))

        return self.work_hours

    def __init__(self, *args, need_count_wh=False, **kwargs):
        super().__init__(*args, **kwargs)
        if need_count_wh:
            self.dttm_work_start_tabel, self.dttm_work_end_tabel, self.work_hours = self._calc_wh()
            self.work_hours = self._round_wh()

    id = models.BigAutoField(primary_key=True, db_index=True)
    code = models.CharField(max_length=256, null=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, null=True)

    employee = models.ForeignKey(
        'base.Employee', null=True, blank=True, on_delete=models.PROTECT, related_name='worker_days',
        verbose_name='Сотрудник',
    )
    # DO_NOTHING т.к. в Employment.delete есть явная чистка рабочих дней для этого трудоустройства
    employment = models.ForeignKey(Employment, on_delete=models.DO_NOTHING, null=True)

    dt = models.DateField()  # todo: make immutable
    dttm_work_start = models.DateTimeField(null=True, blank=True)
    dttm_work_end = models.DateTimeField(null=True, blank=True)
    dttm_work_start_tabel = models.DateTimeField(null=True, blank=True)
    dttm_work_end_tabel = models.DateTimeField(null=True, blank=True)

    type = models.ForeignKey('timetable.WorkerDayType', on_delete=models.PROTECT)

    work_types = models.ManyToManyField(WorkType, through='WorkerDayCashboxDetails')

    is_approved = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='user_created')
    last_edited_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='user_edited')

    comment = models.TextField(null=True, blank=True)
    parent_worker_day = models.ForeignKey(
        'self', on_delete=models.SET_NULL, blank=True, null=True, related_name='child',
        help_text='Используется в подтверждении рабочих дней для того, '
                  'чтобы понимать каким днем из подтв. версии был порожден день в черновике, '
                  'чтобы можно было сопоставить и создать детали рабочего дня')
    work_hours = models.DurationField(default=datetime.timedelta(days=0))

    is_fact = models.BooleanField(default=False)  # плановое или фактическое расписание
    is_vacancy = models.BooleanField(default=False)  # вакансия ли это
    dttm_added = models.DateTimeField(default=timezone.now)
    canceled = models.BooleanField(default=False)
    is_outsource = models.BooleanField(default=False, db_index=True)
    outsources = models.ManyToManyField(
        Network, through=WorkerDayOutsourceNetwork,
        help_text='Аутсорс сети, которые могут откликнуться на данную вакансию', blank=True,
    )
    crop_work_hours_by_shop_schedule = models.BooleanField(
        default=True, verbose_name='Обрезать рабочие часы по времени работы магазина')
    is_blocked = models.BooleanField(
        default=False,
        verbose_name='Защищенный день',
        help_text='Доступен для изменения/подтверждения только определенным группам доступа (настраивается)',
    )
    closest_plan_approved = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='related_facts',
        help_text='Используется в факте (и в черновике и подтв. версии) для связи с планом подтвержденным')

    source = PositiveSmallIntegerField('Источник создания', choices=SOURCES, default=SOURCE_FAST_EDITOR)
    cost_per_hour = models.DecimalField(
        'Стоимость работ за час', max_digits=8, 
        decimal_places=2,
        null=True, blank=True,
    )

    objects = WorkerDayManager.from_queryset(WorkerDayQuerySet)()  # исключает раб. дни у которых employment_id is null
    objects_with_excluded = models.Manager.from_queryset(WorkerDayQuerySet)()

    tracker = FieldTracker(fields=('work_hours', 'type',))

    @property
    def total_cost(self):
        total_cost = None
        if self.cost_per_hour:
            total_cost = self.rounded_work_hours * float(self.cost_per_hour)
        return total_cost

    @property
    def rounded_work_hours(self):
        return round(self.work_hours.total_seconds() / 3600, 2)

    @property
    def is_plan(self):
        return not self.is_fact

    @property
    def is_draft(self):
        return not self.is_approved

    @staticmethod
    def count_work_hours(dttm_work_start, dttm_work_end, break_time):
        work_hours = ((dttm_work_end - dttm_work_start).total_seconds() / 60) - break_time

        if work_hours < 0:
            return datetime.timedelta(0)

        return datetime.timedelta(minutes=work_hours)

    @staticmethod
    def get_fines(dttm_work_start, dttm_work_end, dttm_work_start_plan, dttm_work_end_plan, fines, network):
        arrive_fine = 0
        departure_fine = 0
        def _get_fine_from_range(delta, fines_range):
            for min_threshold, max_threshold, fine in fines_range:
                if delta >= min_threshold and delta <= max_threshold:
                    return fine
            return 0
        if dttm_work_start_plan and dttm_work_end_plan and fines:
            arrive_timedelta = (dttm_work_start - dttm_work_start_plan).total_seconds()
            departure_timedelta = (dttm_work_end_plan - dttm_work_end).total_seconds()
            arrive_step = fines.get('arrive_step')
            departure_step = fines.get('departure_step')
            arrive_fines = fines.get('arrive_fines', [])
            departure_fines = fines.get('departure_fines', [])
            if arrive_timedelta > network.allowed_interval_for_late_arrival.total_seconds() and arrive_step:
                arrive_fine += arrive_step - (int(arrive_timedelta / 60) % arrive_step or arrive_step)
            else:
                arrive_fine += _get_fine_from_range(arrive_timedelta / 60, arrive_fines)
            if departure_timedelta > network.allowed_interval_for_early_departure.total_seconds() and departure_step:
                departure_fine += departure_step - (int(departure_timedelta / 60) % departure_step or departure_step)
            else:
                departure_fine += _get_fine_from_range(departure_timedelta / 60, departure_fines)
        return arrive_fine, departure_fine

    def get_department(self):
        return self.shop
    
    @classmethod
    def get_overlap_qs(cls, user_id=OuterRef('employee__user_id')):
        return cls.objects.filter(
            ~Q(id=OuterRef('id')),
            Q(
                Q(dttm_work_start__lte=OuterRef('dttm_work_start')) &
                Q(dttm_work_end__gt=OuterRef('dttm_work_start'))
            ) |
            Q(
                Q(dttm_work_start__lt=OuterRef('dttm_work_end')) &
                Q(dttm_work_end__gte=OuterRef('dttm_work_end'))
            ) |
            Q(
                Q(dttm_work_start__gte=OuterRef('dttm_work_start')) &
                Q(dttm_work_end__lte=OuterRef('dttm_work_end'))
            ) |
            Q(
                Q(dttm_work_start__lte=OuterRef('dttm_work_start')) &
                Q(dttm_work_end__gte=OuterRef('dttm_work_end'))
            ) | 
            Q(
                Q(dttm_work_start__lte=OuterRef('dttm_work_start')) &
                Q(dttm_work_end__isnull=True)
            ) |
            Q(
                Q(dttm_work_end__gte=OuterRef('dttm_work_end')) &
                Q(dttm_work_start__isnull=True)
            ),
            type__is_dayoff=False,
            employee__user_id=user_id,
            dt=OuterRef('dt'),
            is_fact=OuterRef('is_fact'),
            is_approved=OuterRef('is_approved'),
        )

    @classmethod
    def get_breaktime(cls, network_id, break_calc_field_name):
        break_triplets = Break.get_break_triplets(network_id=network_id)
        breaktime = Value(0, output_field=FloatField())
        if break_triplets:
            whens = [
                When(
                    Q(**{f'{break_calc_field_name}__gte': break_triplet[0]}, **{f'{break_calc_field_name}__lte': break_triplet[1]}) &
                    (
                        Q(employment__position__breaks_id=break_id) |
                        (
                            Q(employment__position__breaks__isnull=True) &
                            Q(employment__shop__settings__breaks_id=break_id)
                        ) |
                        (Q(employment__isnull=True) & Q(shop__settings__breaks_id=break_id))
                    ),
                    then=break_triplet[2]
                )
                for break_id, breaks in break_triplets.items()
                for break_triplet in breaks
            ]
            breaktime = Case(*whens, output_field=FloatField())

        return breaktime

    @staticmethod
    def is_worker_day_vacancy(active_empl_shop_id, worker_day_shop_id, main_work_type_id, worker_day_details_list, is_vacancy=False):
        if active_empl_shop_id and worker_day_shop_id:
            is_vacancy = is_vacancy or active_empl_shop_id != worker_day_shop_id
        if main_work_type_id and worker_day_details_list:
            details_work_type_id = worker_day_details_list[0]['work_type_id'] if isinstance(worker_day_details_list[0], dict) else worker_day_details_list[0].work_type_id
            is_vacancy = is_vacancy or main_work_type_id != details_work_type_id
        return is_vacancy

    @property
    def dt_as_str(self):
        from src.util.models_converter import Converter
        return Converter.convert_date(self.dt)

    @property
    def type_name(self):
        return self.get_type_display()

    @tracker
    def save(self, *args, recalc_fact=True, **kwargs): # todo: aa: частая модель для сохранения, отправлять запросы при сохранении накладно
        self.dttm_work_start_tabel, self.dttm_work_end_tabel, self.work_hours = self._calc_wh()
        self.work_hours = self._round_wh()

        if self.last_edited_by_id is None:
            self.last_edited_by_id = self.created_by_id

        is_new = self.id is None

        res = super().save(*args, **kwargs)
        fines = self.employment.position.wp_fines if self.employment and self.employment.position else None

        # запускаем пересчет часов для факта, если изменились часы в подтвержденном плане
        if recalc_fact and self.shop \
                and (self.shop.network.only_fact_hours_that_in_approved_plan or fines) \
                and self.tracker.has_changed('work_hours') \
                and not self.type.is_dayoff \
                and self.is_plan \
                and self.is_approved:
            fact_qs = WorkerDay.objects.filter(
                dt=self.dt,
                employee_id=self.employee_id,
                is_fact=True,
                type__is_dayoff=False,
                closest_plan_approved_id=self.id,
            ).select_related(
                'shop',
                'employment',
                'employment__position',
                'employment__position__breaks',
                'shop__settings__breaks',
            )
            for fact in fact_qs:
                fact.save()

        if settings.MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE \
                and not self.type.is_dayoff \
                and self.is_plan \
                and self.shop_id \
                and self.employee_id \
                and self.employment_id \
                and self.employment.shop_id != self.shop_id:
            from src.integration.mda.tasks import create_mda_user_to_shop_relation
            transaction.on_commit(lambda: create_mda_user_to_shop_relation.delay(
                username=self.employee.user.username,
                shop_code=self.shop.code,
                debug_info={
                    'wd_id': self.id,
                    'approved': self.is_approved,
                    'is_new': is_new,
                },
            ))
        if self.type.is_reduce_norm or (not is_new and self.tracker.has_changed('type') and WorkerDayType.objects.get(pk=self.tracker.previous('type')).is_reduce_norm):
            transaction.on_commit(lambda: cache.delete_pattern(f"prod_cal_*_*_{self.employee_id}"))

        return res

    def delete(self, *args, **kwargs):
        if self.type.is_reduce_norm:
            transaction.on_commit(lambda: cache.delete_pattern(f"prod_cal_*_*_{self.employee_id}"))
        return super().delete(*args, **kwargs)

    @classmethod
    def get_closest_plan_approved(cls, user_id, priority_shop_id, dttm, record_type=None):
        dt = dttm.date()

        plan_approved_wdays = cls.objects.filter(
            employee__user_id=user_id,
            dt__gte=dt - datetime.timedelta(1),
            dt__lte=dt + datetime.timedelta(1),
            is_approved=True,
            is_fact=False,
            type__is_dayoff=False,
        ).annotate(
            is_equal_shops=Case(
                When(shop_id=priority_shop_id, then=True),
                default=False, output_field=BooleanField()
            ),
            dttm_work_start_diff=Abs(Cast(Extract(dttm - F('dttm_work_start'), 'epoch'), IntegerField())),
            dttm_work_end_diff=Abs(Cast(Extract(dttm - F('dttm_work_end'), 'epoch'), IntegerField())),
            dttm_diff_min=Least(
                F('dttm_work_start_diff'),
                F('dttm_work_end_diff'),
            ),
        ).filter(
            dttm_diff_min__lt=F('shop__network__max_plan_diff_in_seconds')
        ).prefetch_related(
            Prefetch(
                'worker_day_details',
                queryset=WorkerDayCashboxDetails.objects.select_related('work_type'),
                to_attr='worker_day_details_list',
            )
        )

        order_by = ['-is_equal_shops']
        if record_type == AttendanceRecords.TYPE_COMING:
            order_by.append('dttm_work_start_diff')
        if record_type == AttendanceRecords.TYPE_LEAVING:
            order_by.append('dttm_work_end_diff')
        order_by.append('dttm_diff_min')

        closest_plan_approved = plan_approved_wdays.order_by(*order_by).first()

        if not record_type and closest_plan_approved:
            if closest_plan_approved.dttm_diff_min == closest_plan_approved.dttm_work_start_diff:
                record_type = AttendanceRecords.TYPE_COMING

            if closest_plan_approved.dttm_diff_min == closest_plan_approved.dttm_work_end_diff:
                record_type = AttendanceRecords.TYPE_LEAVING

        return closest_plan_approved, record_type

    @classmethod
    def check_work_time_overlap(cls, employee_days_q=None, employee_id=None, employee_id__in=None, user_id=None,
                                user_id__in=None, dt=None, dt__in=None, is_fact=None, is_approved=None, raise_exc=True, exc_cls=None):
        """
        Проверка наличия пересечения рабочего времени
        """
        if not (employee_days_q or employee_id or employee_id__in or user_id or user_id__in):
            return

        lookup = {
            'type__is_dayoff': False,
        }
        if is_fact is not None:
            lookup['is_fact'] = is_fact

        if is_approved is not None:
            lookup['is_approved'] = is_approved

        if employee_id:
            lookup['employee__user__employees__id'] = employee_id

        if employee_id__in:
            lookup['employee__user__employees__id__in'] = employee_id__in

        if user_id:
            lookup['employee__user_id'] = user_id

        if user_id__in:
            lookup['employee__user_id__in'] = user_id__in

        if dt:
            lookup['dt'] = dt

        if dt__in:
            lookup['dt__in'] = dt__in

        q = Q(**lookup)
        if employee_days_q:
            q &= employee_days_q

        overlaps_qs = cls.objects.filter(q).annotate(
            has_overlap=Exists(cls.get_overlap_qs())
        ).filter(
            has_overlap=True,
        ).values('employee__user__last_name', 'employee__user__first_name', 'dt').distinct()

        overlaps = list(overlaps_qs)

        if overlaps and raise_exc:
            original_exc = WorkTimeOverlap(overlaps=overlaps)
            if exc_cls:
                raise exc_cls(str(original_exc))
            raise original_exc

        return overlaps

    @classmethod
    def check_main_work_hours_norm(cls, dt_from, dt_to, shop_id, employee_id=None, employee_id__in=None, raise_exc=True, exc_cls=None):
        """
        Проверка, что в основном графике количество часов не может быть больше, чем по норме часов
        """
        from src.timetable.worker_day.stat import WorkersStatsGetter
        if not (employee_id or employee_id__in):
            return

        networks = list(filter(lambda x: x.settings_values_prop.get('check_main_work_hours_norm', False), Network.objects.all()))

        employee_filter = {
            'user__network__in': networks,
        }

        if employee_id:
            employee_filter['id'] = employee_id

        if employee_id__in:
            employee_filter['id__in'] = employee_id__in

        employees = {e.id: e for e in Employee.objects.filter(**employee_filter).select_related('user__network')}

        if not employees:
            return

        date_ranges = map(lambda x: (x.replace(day=1), x), pd.date_range(dt_from.replace(day=1), dt_to + relativedelta(day=31), freq='1M').date)

        data_greater_norm = []
        norm_key = getattr(settings, 'TIMESHEET_DIVIDER_SAWH_HOURS_KEY', 'curr_month')

        for dt_from, dt_to in date_ranges:
            stats = WorkersStatsGetter(
                dt_from=dt_from,
                dt_to=dt_to,
                employee_id__in=employees.keys(),
                shop_id=shop_id,
                use_cache=False,
            ).run()

            stats_df = pd.DataFrame(
                columns=['employee_id', 'last_name', 'first_name', 'norm', 'total_work_hours'],
                data=list(
                    map(
                        lambda x: (
                            x[0],
                            employees[x[0]].user.last_name,
                            employees[x[0]].user.first_name,
                            x[1].get("plan", {}).get("approved", {}).get("sawh_hours", {}).get(norm_key, 0),
                            x[1].get("plan", {}).get("approved", {}).get("work_hours", {}).get("all_shops_main", 0),
                        ),
                        stats.items(),
                    )
                )
            )

            stats_df['difference'] = stats_df.total_work_hours - stats_df.norm
            stats_df['dt_from'] = dt_from
            stats_df['dt_to'] = dt_to

            data_greater_norm.extend(stats_df[stats_df['difference'] > 0].to_dict('records'))

        if data_greater_norm and raise_exc:
            original_exc = MainWorkHoursGreaterThanNorm(exc_data=data_greater_norm)
            if exc_cls:
                raise exc_cls(str(original_exc))
            raise original_exc

        return data_greater_norm

    @classmethod
    def check_multiple_workday_types(cls, employee_days_q=None, employee_id=None, employee_id__in=None, user_id=None,
                                user_id__in=None, dt=None, dt__in=None, is_fact=None, is_approved=None, raise_exc=True,
                                exc_cls=None):
        """
        Проверка,
            - не может быть нескольких нерабочих дней на 1 дату
            - не может быть одновременные нерабочий день и рабочий день на 1 дату, кроме случаев
                когда у нерабочего типа дня есть allowed_additional_types
        """
        if not (employee_days_q or employee_id or employee_id__in or user_id or user_id__in):
            return

        lookup = {
            'type__is_dayoff': True,
        }
        if is_fact is not None:
            lookup['is_fact'] = is_fact

        if is_approved is not None:
            lookup['is_approved'] = is_approved

        if employee_id:
            lookup['employee__user__employees__id'] = employee_id

        if employee_id__in:
            lookup['employee__user__employees__id__in'] = employee_id__in

        if user_id:
            lookup['employee__user_id'] = user_id

        if user_id__in:
            lookup['employee__user_id__in'] = user_id__in

        if dt:
            lookup['dt'] = dt

        if dt__in:
            lookup['dt__in'] = dt__in

        q = Q(**lookup)
        if employee_days_q:
            q &= employee_days_q

        has_multiple_workday_types_qs = cls.objects.filter(q).annotate(
            has_multiple_dayoff_types=Exists(
                WorkerDay.objects.filter(
                    ~Q(id=OuterRef('id')),
                    type__is_dayoff=True,
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=OuterRef('is_fact'),
                    is_approved=OuterRef('is_approved'),
                )
            ),
            has_dayoff_and_not_allowed_workday_types=Exists(
                WorkerDay.objects.filter(
                    ~Q(id=OuterRef('id')),
                    type__is_dayoff=False,
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=OuterRef('is_fact'),
                    is_approved=OuterRef('is_approved'),
                ).exclude(
                    type__allowed_as_additional_for=OuterRef('type'),
                )
            ),
        ).filter(
            Q(has_multiple_dayoff_types=True) | Q(has_dayoff_and_not_allowed_workday_types=True),
        ).values('employee__user__last_name', 'employee__user__first_name', 'dt').distinct()

        multiple_workday_types_data = list(has_multiple_workday_types_qs)

        if multiple_workday_types_data and raise_exc:
            original_exc = MultipleWDTypesOnOneDateForOneEmployee(multiple_workday_types_data=multiple_workday_types_data)
            if exc_cls:
                raise exc_cls(str(original_exc))
            raise original_exc

        return multiple_workday_types_data

    @classmethod
    def check_tasks_violations(cls, is_fact, is_approved, employee_days_q=None, employee_id=None, employee_id__in=None, user_id=None, user_id__in=None, dt=None,
                              dt__in=None, raise_exc=True, exc_cls=None):
        """
        Проверка наличия задач
        """
        lookup = {
            'is_fact': is_fact,
            'is_approved': is_approved,
        }
        if employee_id:
            lookup['employee_id'] = employee_id

        if employee_id__in:
            lookup['employee__id__in'] = employee_id__in

        if user_id:
            lookup['employee__user_id'] = user_id

        if user_id__in:
            lookup['employee__user_id__in'] = user_id__in

        if dt:
            lookup['dt'] = dt

        if dt__in:
            lookup['dt__in'] = dt__in

        q = Q(**lookup)
        if employee_days_q:
            q &= employee_days_q

        tasks_subq = Task.objects.filter(
            Q(dt=OuterRef('dt')),
            Q(employee_id=OuterRef('employee_id')),
            #Q(operation_type__shop_id=OuterRef('shop_id')),  # у выходных нету привязки к подразделению
        )

        wds_with_task_violation = WorkerDay.objects.filter(q).annotate(
            task_least_start_time=Subquery(
                tasks_subq.order_by('dttm_start_time').values('dttm_start_time')[:1]
            ),
            task_greatest_end_time=Subquery(
                tasks_subq.order_by('-dttm_end_time').values('dttm_end_time')[:1]
            ),
        ).filter(
            Q(
                Q(type__is_dayoff=False) &
                Q(
                    Q(dttm_work_start__gt=F('task_least_start_time')) |
                    Q(dttm_work_end__lt=F('task_greatest_end_time'))
                )
            ) |
            Q(
                ~Q(type__is_dayoff=False) &
                Q(task_least_start_time__isnull=False)
            )
        ).values(
            'employee__user__last_name',
            'employee__user__first_name',
            'dt',
            'task_least_start_time',
            'task_greatest_end_time',
            'dttm_work_start',
            'dttm_work_end',
        ).distinct()

        task_violations = list(wds_with_task_violation)

        if task_violations and raise_exc:
            original_exc = WorkDayTaskViolation(task_violations=task_violations)
            if exc_cls:
                raise exc_cls(str(original_exc))
            raise original_exc

        return task_violations

    # TODO: рефакторинг: не дублировать код в проверках -- вынести в классы?
    @classmethod
    def check_only_one_wday_on_date(cls, employee_days_q=None, employee_id=None, employee_id__in=None, user_id=None,
                                user_id__in=None, dt=None, dt__in=None, is_fact=None, is_approved=None, raise_exc=True,
                                exc_cls=None):
        """
        Проверка, что на 1 дату у сотрудника не создается несколько дней
        """
        if not (employee_days_q or employee_id or employee_id__in or user_id or user_id__in):
            return

        lookup = {}
        if is_fact is not None:
            lookup['is_fact'] = is_fact

        if is_approved is not None:
            lookup['is_approved'] = is_approved

        if employee_id:
            lookup['employee__user__employees__id'] = employee_id

        if employee_id__in:
            lookup['employee__user__employees__id__in'] = employee_id__in

        if user_id:
            lookup['employee__user_id'] = user_id

        if user_id__in:
            lookup['employee__user_id__in'] = user_id__in

        if dt:
            lookup['dt'] = dt

        if dt__in:
            lookup['dt__in'] = dt__in

        q = Q(**lookup)
        if employee_days_q:
            q &= employee_days_q

        has_another_wday_on_date_qs = cls.objects.filter(q).annotate(
            has_another_wday_on_date=Exists(
                WorkerDay.objects.filter(
                    ~Q(id=OuterRef('id')),
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=OuterRef('is_fact'),
                    is_approved=OuterRef('is_approved'),
                )
            )
        ).filter(
            has_another_wday_on_date=True,
        ).values('employee__user__last_name', 'employee__user__first_name', 'dt').distinct()

        exc_data = list(has_another_wday_on_date_qs)

        if exc_data and raise_exc:
            original_exc = HasAnotherWdayOnDate(exc_data=exc_data)
            if exc_cls:
                raise exc_cls(str(original_exc))
            raise original_exc

        return exc_data

    @classmethod
    def get_closest_plan_approved_q(
            cls, employee_id, dt, dttm_work_start, dttm_work_end, delta_in_secs, use_annotated_filter=True):
        plan_approved_qs = WorkerDay.objects.filter(
            employee_id=employee_id,
            dt=dt,
            is_fact=False,
            is_approved=True,
            type__is_dayoff=False,
        )
        if use_annotated_filter:
            plan_approved_qs = plan_approved_qs.annotate(
                plan_approved_count=Subquery(WorkerDay.objects.filter(
                    employee_id=OuterRef(employee_id) if isinstance(employee_id, OuterRef) else employee_id,
                    dt=OuterRef(dt) if isinstance(dt, OuterRef) else dt,
                    is_fact=False,
                    is_approved=True,
                    type__is_dayoff=False,
                ).values(
                    'employee_id',
                    'dt',
                    'is_fact',
                    'is_approved',
                ).annotate(
                    objs_count=Count('*'),
                ).values('objs_count')[:1], output_field=IntegerField())
            ).filter(
                Q(Q(plan_approved_count__gt=1) & Q(
                    Q(dttm_work_start__gte=dttm_work_start - datetime.timedelta(seconds=delta_in_secs)) &
                    Q(dttm_work_start__lte=dttm_work_start + datetime.timedelta(seconds=delta_in_secs)),
                    Q(dttm_work_end__gte=dttm_work_end - datetime.timedelta(seconds=delta_in_secs)) &
                    Q(dttm_work_end__lte=dttm_work_end + datetime.timedelta(seconds=delta_in_secs))
                )) | Q(plan_approved_count=1),
            )
        else:
            plan_approved_qs = plan_approved_qs.filter(
                Q(dttm_work_start__gte=dttm_work_start - datetime.timedelta(seconds=delta_in_secs)) &
                Q(dttm_work_start__lte=dttm_work_start + datetime.timedelta(seconds=delta_in_secs)) &
                Q(dttm_work_end__gte=dttm_work_end - datetime.timedelta(seconds=delta_in_secs)) &
                Q(dttm_work_end__lte=dttm_work_end + datetime.timedelta(seconds=delta_in_secs))
            )
        return plan_approved_qs

    @classmethod
    def set_closest_plan_approved(cls, q_obj, delta_in_secs, is_approved=None):
        """
        Метод проставления closest_plan_approved в факте

        :param q_obj: Q объект для фильтрации дней, в которых нужно проставить closest_plan_approved
        :param is_approved: проставляем в подтвержденной версии факта или в черновике
        :param delta_in_secs: максимальное отклонения в секундах времени начала и времени окончания в плане и в факте
        """
        if q_obj:
            filter_kwargs = dict(
                is_fact=True,
                closest_plan_approved__isnull=True,
            )
            if is_approved is not None:
                filter_kwargs['is_approved'] = is_approved

            qs = cls.objects.filter(
                q_obj, **filter_kwargs,
            ).annotate(
                plan_approved_count=Subquery(WorkerDay.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=False,
                    is_approved=True,
                    type__is_dayoff=False,
                ).values(
                    'employee_id',
                    'dt',
                    'is_fact',
                    'is_approved',
                ).annotate(
                    objs_count=Count('*'),
                ).values('objs_count')[:1], output_field=IntegerField())
            )

            qs.filter(plan_approved_count__gt=1).update(
                closest_plan_approved=Subquery(cls.get_closest_plan_approved_q(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    dttm_work_start=OuterRef('dttm_work_start'),
                    dttm_work_end=OuterRef('dttm_work_end'),
                    delta_in_secs=delta_in_secs,
                    use_annotated_filter=False,
                ).annotate(
                    order_by_val=RawSQL("""LEAST(
                        ABS(EXTRACT(EPOCH FROM (U0."dttm_work_start" - "timetable_workerday"."dttm_work_start"))),
                        ABS(EXTRACT(EPOCH FROM (U0."dttm_work_end" - "timetable_workerday"."dttm_work_end")))
                    )""", [])
                ).order_by(
                    'order_by_val',
                ).values('id')[:1])
            )
            qs.filter(plan_approved_count=1).update(
                closest_plan_approved=Subquery(WorkerDay.objects.filter(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=False,
                    is_approved=True,
                    type__is_dayoff=False,
                ).values('id')[:1])
            )


class TimesheetItem(AbstractModel):
    TIMESHEET_TYPE_FACT = 'F'
    TIMESHEET_TYPE_MAIN = 'M'
    TIMESHEET_TYPE_ADDITIONAL = 'A'

    TIMESHEET_TYPE_CHOICES = (
        (TIMESHEET_TYPE_FACT, _('Fact')),  # все оплачиваемые часы
        (TIMESHEET_TYPE_MAIN, _('Main')),  # рабочие часы, которые идут в осн. табель
        (TIMESHEET_TYPE_ADDITIONAL, _('Additional')),  # рабочие часы, которые идут в доп. табель
    )

    SOURCE_TYPE_PLAN = 'P'
    SOURCE_TYPE_FACT = 'F'
    SOURCE_TYPE_MANUAL = 'M'
    SOURCE_TYPE_SYSTEM = 'S'

    SOURCE_TYPES = (
        (SOURCE_TYPE_PLAN, _('Planned timetable')),  # плановый график
        (SOURCE_TYPE_FACT, _('Actual timetable')),  # фактический график
        (SOURCE_TYPE_MANUAL, _('Manual changes')),  # ручные корректировки (заготовка, пока нет такого)
        (SOURCE_TYPE_SYSTEM, _('Determined by the system')),  # определены системой
    )

    timesheet_type = models.CharField(
        max_length=32, choices=TIMESHEET_TYPE_CHOICES, verbose_name='Тип табеля')
    shop = models.ForeignKey(
        'base.Shop', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Поздразделение выхода сотрудника',
        help_text='Для выходных магазин берется из трудоустройства',
    )
    position = models.ForeignKey(
        'base.WorkerPosition', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Должность',
        help_text='Определяется на основе должности трудоустройства, либо через сопоставление с типами работ, если включена настройка ')  # TODO: добавить название настройки
    work_type_name = models.ForeignKey(
        'timetable.WorkTypeName', on_delete=models.PROTECT, null=True, blank=True, verbose_name='Тип работ',
        help_text='Определяется на основе первого типа работ в рабочем дне',  # TODO: поддержка нескольких типов работ для 1 раб. дня?
    )
    employee = models.ForeignKey('base.Employee', on_delete=models.CASCADE, verbose_name='Сотрудник')
    dt = models.DateField()
    day_type = models.ForeignKey(
        'timetable.WorkerDayType', on_delete=models.PROTECT, verbose_name='Тип дня',
    )
    dttm_work_start = models.DateTimeField(null=True, blank=True)
    dttm_work_end = models.DateTimeField(null=True, blank=True)
    day_hours = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.00"))
    night_hours = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal("0.00"))
    source = models.CharField(
        choices=SOURCE_TYPES, max_length=12, blank=True,
        verbose_name='Источник данных',
    )

    class Meta:
        verbose_name = 'Запись в табеле учета рабочего времени'
        verbose_name_plural = 'Записи в табеле учета рабочего времени'

    def __str__(self):
        return '{}, {}, {}, {}, {}, {}'.format(
            self.id,
            self.dt,
            self.employee_id,
            self.day_type_id,
            self.timesheet_type,
            self.day_hours + self.night_hours,
        )


class WorkerDayCashboxDetailsManager(models.Manager):
    def qos_current_version(self):
        return super().get_queryset().select_related('worker_day').filter(worker_day__child__id__isnull=True)

    def qos_initial_version(self):
        return super().get_queryset().select_related('worker_day').filter(worker_day__parent_worker_day__isnull=True)

    def qos_filter_version(self, checkpoint):
        """
        :param checkpoint: 0 or 1 / True of False. If 1 -- current version, else -- initial
        :return:
        """
        if checkpoint:
            return self.qos_current_version()
        else:
            return self.qos_initial_version()


class WorkerDayCashboxDetails(AbstractActiveModel):
    class Meta:
        verbose_name = 'Детали в течение рабочего дня'

    id = models.BigAutoField(primary_key=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.CASCADE, null=True, blank=True, related_name='worker_day_details')
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, null=True, blank=True)
    work_part = models.FloatField(default=1.0)

    def __str__(self):
        return '{}, {}, {}, id: {}'.format(
            # self.worker_day.worker.last_name,
            self.worker_day,
            self.work_part,
            self.work_type.work_type_name.name if self.work_type else None,
            self.id,
        )

    def delete(self, *args, **kwargs):
        super(AbstractActiveModel, self).delete(*args, **kwargs)

    objects = WorkerDayCashboxDetailsManager()


class ShopMonthStat(AbstractModel):
    class Meta(object):
        unique_together = (('shop', 'dt'),)
        verbose_name = 'Статистика по мгазину за месяц'
        verbose_name_plural = 'Статистики по мгазинам за месяц'

    READY = 'R'
    PROCESSING = 'P'
    ERROR = 'E'
    NOT_DONE = 'N'

    STATUS = [
        (READY, 'Готово'),
        (PROCESSING, 'В процессе'),
        (ERROR, 'Ошибка'),
        (NOT_DONE, 'График не составлен'),
    ]

    def __str__(self):
        return 'id: {}, shop: {}, status: {}'.format(
            self.id,
            self.shop,
            self.status
        )

    id = models.BigAutoField(primary_key=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, related_name='timetable')
    status_message = models.CharField(max_length=256, null=True, blank=True)
    dt = models.DateField()
    status = models.CharField(choices=STATUS, default=NOT_DONE, max_length=1)
    dttm_status_change = models.DateTimeField()
    is_approved = models.BooleanField(default=False)

    # statistics
    fot = models.IntegerField(default=0, blank=True, null=True)
    lack = models.SmallIntegerField(default=0, blank=True, null=True)  # хранится покрытие, TODO: переименовать поле
    idle = models.SmallIntegerField(default=0, blank=True, null=True)
    workers_amount = models.IntegerField(default=0, blank=True, null=True)
    revenue = models.IntegerField(default=0, blank=True, null=True)
    fot_revenue = models.IntegerField(default=0, blank=True, null=True)
    predict_needs = models.IntegerField(default=0, blank=True, null=True, verbose_name='Количество часов по нагрузке')

    task_id = models.CharField(max_length=256, null=True, blank=True)

    def get_department(self):
        return self.shop


class AttendanceRecords(AbstractModel):
    class Meta(object):
        verbose_name = 'Данные УРВ'

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
        (TYPE_NO_TYPE, 'no_type')
    )

    TYPE_2_DTTM_FIELD = {
        TYPE_COMING: 'dttm_work_start',
        TYPE_LEAVING: 'dttm_work_end',
    }

    dt = models.DateField()
    dttm = models.DateTimeField()
    type = models.CharField(max_length=1, choices=RECORD_TYPES)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    employee = models.ForeignKey(Employee, on_delete=models.PROTECT, null=True)
    verified = models.BooleanField(default=True)
    terminal = models.BooleanField(default=False, help_text='Отметка с теримнала')

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT) # todo: or should be to shop? fucking logic

    def __str__(self):
        return 'UserId: {}, type: {}, dttm: {}'.format(self.user_id, self.type, self.dttm)

    @staticmethod
    def get_day_data(dttm: datetime.datetime, user, shop, initial_record_type=None):
        dt = dttm.date()

        employment = Employment.objects.get_active_empl_by_priority(
            network_id=user.network_id, employee__user=user,
            dt=dt,
            priority_shop_id=shop.id,
            annotate_main_work_type_id=True,
        ).first()
        if not employment:
            raise ValidationError(_('You have no active employment'))
        employee_id = employment.employee_id

        closest_plan_approved, calculated_record_type = WorkerDay.get_closest_plan_approved(
            user_id=user.id,
            priority_shop_id=shop.id,
            dttm=dttm,
            record_type=initial_record_type,
        )

        if closest_plan_approved is None:
            if not initial_record_type:
                record_type = AttendanceRecords.TYPE_COMING
                record = AttendanceRecords.objects.filter(
                    shop=shop,
                    user=user,
                    dt=dt,
                    employee_id=employee_id,
                ).order_by('dttm').first()
                if record and record.dttm < dttm:
                    record_type = AttendanceRecords.TYPE_LEAVING
            else:
                record_type = initial_record_type
        else:
            record_type = initial_record_type or calculated_record_type
            employee_id = closest_plan_approved.employee_id
            employment = Employment.objects.annotate_main_work_type_id().filter(
                id=closest_plan_approved.employment_id,
            ).first()
            if not employment:
                raise ValidationError(_('You have no active employment'))
            dt = closest_plan_approved.dt

        return employee_id, employment, dt, record_type, closest_plan_approved

    def _create_wd_details(self, dt, fact_approved, active_user_empl, closest_plan_approved):
        if closest_plan_approved:
            fact_shop_details_list = []
            for plan_details in closest_plan_approved.worker_day_details_list:
                work_type = plan_details.work_type if (
                            fact_approved.shop_id == closest_plan_approved.shop_id) else WorkType.objects.filter(
                    shop_id=fact_approved.shop_id,
                    work_type_name_id=plan_details.work_type.work_type_name_id,
                ).first()
                if not work_type.dttm_deleted:
                    fact_shop_details_list.append(
                        WorkerDayCashboxDetails(
                            work_part=plan_details.work_part,
                            worker_day=fact_approved,
                            work_type=work_type,
                        )
                    )

            if fact_shop_details_list:
                WorkerDayCashboxDetails.objects.bulk_create(fact_shop_details_list)
                return

        if active_user_empl:
            employment_work_type = EmploymentWorkType.objects.filter(
                Q(work_type__dttm_deleted__isnull=True) | Q(work_type__dttm_deleted__gte=timezone.now()),
                employment=active_user_empl,
            ).order_by('-priority').select_related('work_type').first()
            if employment_work_type:
                if active_user_empl.shop_id == fact_approved.shop_id:
                    work_type = employment_work_type.work_type
                else:
                    work_type = WorkType.objects.filter(
                        Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=timezone.now()),
                        shop_id=fact_approved.shop_id,
                        work_type_name_id=employment_work_type.work_type.work_type_name_id,
                    ).first()

                if work_type:
                    WorkerDayCashboxDetails.objects.create(
                        work_part=1,
                        worker_day=fact_approved,
                        work_type=work_type,
                    )
                    return

        work_type = WorkType.objects.filter(
            Q(dttm_deleted__isnull=True) | Q(dttm_deleted__gte=timezone.now()),
            shop_id=fact_approved.shop_id,
        ).first()
        if work_type:
            WorkerDayCashboxDetails.objects.create(
                work_part=1,
                worker_day=fact_approved,
                work_type=work_type,
            )
            return

    def _create_or_update_not_approved_fact(self, fact_approved):
        # TODO: попробовать найти вариант без удаления workerday?
        WorkerDay.objects.filter(
            Q(last_edited_by__isnull=True) | Q(type_id=WorkerDay.TYPE_EMPTY),
            dt=fact_approved.dt,
            employee_id=fact_approved.employee_id,
            is_fact=True,
            is_approved=False,
        ).delete()

        other_facts_approved = list(WorkerDay.objects.filter(
            dt=fact_approved.dt,
            employee_id=fact_approved.employee_id,
            is_fact=True,
            is_approved=True,
            last_edited_by__isnull=True,
        ).exclude(
            id=fact_approved.id,
        ))
        facts_approved_to_copy = other_facts_approved + [fact_approved]
        for fact_approved_to_copy in facts_approved_to_copy:
            try:
                with transaction.atomic():
                    not_approved = WorkerDay.objects.create(
                        shop=fact_approved_to_copy.shop,
                        employee_id=fact_approved_to_copy.employee_id,
                        employment=fact_approved_to_copy.employment,
                        dttm_work_start=fact_approved_to_copy.dttm_work_start,
                        dttm_work_end=fact_approved_to_copy.dttm_work_end,
                        dt=fact_approved_to_copy.dt,
                        is_fact=fact_approved_to_copy.is_fact,
                        is_approved=False,
                        type=fact_approved_to_copy.type,
                        is_vacancy=fact_approved_to_copy.is_vacancy,
                        is_outsource=fact_approved_to_copy.is_outsource,
                        created_by_id=fact_approved_to_copy.created_by_id,
                        last_edited_by_id=fact_approved_to_copy.last_edited_by_id,
                        closest_plan_approved_id=fact_approved_to_copy.closest_plan_approved_id,
                        source=WorkerDay.SOURCE_AUTO_FACT,
                    )
                    WorkerDay.check_work_time_overlap(
                        employee_id=fact_approved.employee_id, dt=fact_approved.dt, is_fact=True, is_approved=False)
            except WorkTimeOverlap as e:
                pass
                # TODO: запись в debug лог + тест
            else:
                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=not_approved,
                            work_type_id=details.work_type_id,
                        )
                        for details in fact_approved_to_copy.worker_day_details.all()
                    ]
                )

    def _get_base_fact_approved_qs(self, closest_plan_approved, shop_id):
        return WorkerDay.objects.annotate_value_equality(
            'is_closest_plan_approved_equal', 'closest_plan_approved', closest_plan_approved,
        ).annotate_value_equality(
            'is_equal_shops', 'shop_id', shop_id,
        ).annotate(
            diff_between_tick_and_work_start_seconds=Cast(
                Extract(self.dttm - F('dttm_work_start'), 'epoch'), IntegerField()),
        )

    def _get_fact_approved_extra_q(self, closest_plan_approved):
        fact_approved_extra_q = Q(closest_plan_approved=closest_plan_approved) if closest_plan_approved else Q()
        if self.type == self.TYPE_LEAVING:
            fact_approved_extra_q |= Q(
                dttm_work_start__isnull=False,
                diff_between_tick_and_work_start_seconds__lte=F('shop__network__max_work_shift_seconds'),
            )
        return fact_approved_extra_q

    def _is_one_arrival_and_departure_for_associated_wdays(self):
        return self.user.network.settings_values_prop.get('one_arrival_and_departure_for_associated_wdays')

    def _search_associated_wday(self, plan_approved):
        return WorkerDay.objects.filter(
            is_fact=False,
            is_approved=True,
            employee_id=plan_approved.employee_id,
            shop_id=plan_approved.shop_id,
            dttm_work_end=plan_approved.dttm_work_start,
            type__is_dayoff=False,
        ).select_related(
            'employment',
        ).prefetch_related(
            Prefetch(
                'worker_day_details',
                queryset=WorkerDayCashboxDetails.objects.select_related('work_type'),
                to_attr='worker_day_details_list',
            )
        ).first()

    def _handle_one_arrival_and_departure_for_associated_wdays(
            self, plan_approved, recalc_fact_from_att_records=False):
        associated_wdays_chain = [plan_approved]
        associated_wday = self._search_associated_wday(plan_approved)
        if not associated_wday:
            return
        else:
            associated_wdays_chain.append(associated_wday)

        while associated_wday:
            associated_wday = self._search_associated_wday(associated_wday)
            if associated_wday:
                associated_wdays_chain.append(associated_wday)

        associated_wdays_chain.reverse()

        max_plan_diff_in_seconds = datetime.timedelta(seconds=self.shop.network.max_plan_diff_in_seconds)
        dttm_from = associated_wdays_chain[0].dttm_work_start - max_plan_diff_in_seconds
        dttm_to = associated_wdays_chain[-1].dttm_work_end + max_plan_diff_in_seconds
        dttm_coming = AttendanceRecords.objects.filter(
            employee_id=self.employee_id,
            shop_id=self.shop_id,
            type=AttendanceRecords.TYPE_COMING,
            dttm__gte=dttm_from,
            dttm__lte=associated_wdays_chain[-1].dttm_work_end,
        ).order_by('dttm').values_list('dttm', flat=True).first() or WorkerDay.objects.filter(
            last_edited_by__isnull=False,
            is_fact=True,
            is_approved=True,
            employee_id=plan_approved.employee_id,
            shop_id=plan_approved.shop_id,
            dttm_work_start__gte=dttm_from,
            dttm_work_start__lte=associated_wdays_chain[-1].dttm_work_end,
            type__is_dayoff=False,
        ).order_by('dttm_work_start').values_list('dttm_work_start', flat=True).first()
        dttm_leaving = AttendanceRecords.objects.filter(
            employee_id=self.employee_id,
            shop_id=self.shop_id,
            type=AttendanceRecords.TYPE_LEAVING,
            dttm__gte=associated_wdays_chain[0].dttm_work_start,
            dttm__lte=dttm_to,
        ).order_by('dttm').values_list('dttm', flat=True).last() or WorkerDay.objects.filter(
            last_edited_by__isnull=False,
            is_fact=True,
            is_approved=True,
            employee_id=plan_approved.employee_id,
            shop_id=plan_approved.shop_id,
            dttm_work_end__gte=associated_wdays_chain[0].dttm_work_start,
            dttm_work_end__lte=dttm_to,
            type__is_dayoff=False,
        ).order_by('dttm_work_end').values_list('dttm_work_end', flat=True).last()

        if not (dttm_coming and dttm_leaving):
            return

        wdays_to_clean_qs = WorkerDay.objects.filter(
            Q(
                Q(dttm_work_start__gte=dttm_from) | Q(dttm_work_start__isnull=True),
                Q(dttm_work_end__lte=dttm_to) | Q(dttm_work_end__isnull=True),
                employee_id=self.employee_id,
                shop_id=self.shop_id,
                is_fact=True,
                last_edited_by__isnull=True,
            )
            | Q(
                dt__range=[dttm_from.date(), dttm_to.date()],
                employee_id=self.employee_id,
                is_fact=True,
                type_id=WorkerDay.TYPE_EMPTY,
            )
        )
        wdays_to_clean_qs.delete()
        associated_wdays_count = len(associated_wdays_chain)
        for idx, associated_wday in enumerate(associated_wdays_chain):
            is_first = idx == 0
            is_last = idx == associated_wdays_count - 1
            try:
                with transaction.atomic():
                    fact_approved = WorkerDay.objects.create(
                        dt=associated_wday.dt,
                        employee_id=associated_wday.employee_id,
                        is_fact=True,
                        is_approved=True,
                        closest_plan_approved=associated_wday,
                        shop_id=associated_wday.shop_id,
                        employment=associated_wday.employment,
                        type_id=associated_wday.type_id,
                        dttm_work_start=dttm_coming if is_first else associated_wday.dttm_work_start,
                        dttm_work_end=dttm_leaving if is_last else associated_wday.dttm_work_end,
                        is_vacancy=associated_wday.is_vacancy,
                        source=WorkerDay.RECALC_FACT_FROM_ATT_RECORDS if recalc_fact_from_att_records else WorkerDay.SOURCE_AUTO_FACT,
                    )
                    WorkerDay.check_work_time_overlap(
                            employee_id=associated_wday.employee_id, dt=associated_wday.dt, is_fact=True, is_approved=True)
            except WorkTimeOverlap:
                pass
            else:
                if fact_approved.type.has_details:
                    self._create_wd_details(associated_wday.dt, fact_approved, associated_wday.employment, associated_wday)
                self._create_or_update_not_approved_fact(fact_approved)

    def save(self, *args, recalc_fact_from_att_records=False, **kwargs):
        """
        Создание WorkerDay при занесении отметок.
        """
        # рефакторинг
        employee_id, active_user_empl, dt, record_type, closest_plan_approved = self.get_day_data(
            self.dttm, self.user, self.shop, self.type)
        self.dt = dt
        self.fact_wd = None
        self.type = self.type or record_type
        self.employee_id = self.employee_id or employee_id
        res = super(AttendanceRecords, self).save(*args, **kwargs)

        if self.type == self.TYPE_NO_TYPE:
            return res

        with transaction.atomic():
            if self.type == self.TYPE_LEAVING and \
                    closest_plan_approved and \
                    self._is_one_arrival_and_departure_for_associated_wdays() and\
                    self._search_associated_wday(closest_plan_approved):
                self._handle_one_arrival_and_departure_for_associated_wdays(closest_plan_approved)
            else:
                base_fact_approved_qs = self._get_base_fact_approved_qs(closest_plan_approved, shop_id=self.shop_id)
                fact_approved_extra_q = self._get_fact_approved_extra_q(closest_plan_approved)
                fact_approved = base_fact_approved_qs.filter(
                    fact_approved_extra_q,
                    dt=self.dt,
                    employee_id=self.employee_id,
                    is_fact=True,
                    is_approved=True,
                ).select_related('type').order_by('-is_equal_shops', '-is_closest_plan_approved_equal').first()

                if fact_approved:
                    self.fact_wd = fact_approved
                    if fact_approved.last_edited_by_id:
                        return res

                    # если это отметка о приходе, то не перезаписываем время начала работы в графике
                    # если время отметки больше, чем время начала работы в существующем графике
                    skip_condition = (self.type == self.TYPE_COMING) and \
                                     fact_approved.dttm_work_start and self.dttm > fact_approved.dttm_work_start
                    if skip_condition:
                        return res

                    setattr(fact_approved, self.TYPE_2_DTTM_FIELD[self.type], self.dttm)
                    # TODO: проставление такого же типа как в плане? (тест + проверить)
                    setattr(fact_approved, 'type_id',
                            closest_plan_approved.type_id if closest_plan_approved else WorkerDay.TYPE_WORKDAY)
                    setattr(fact_approved, 'shop_id', self.shop_id)
                    setattr(fact_approved, 'last_edited_by', None)
                    setattr(fact_approved, 'created_by', None)
                    if not fact_approved.is_vacancy and closest_plan_approved:
                        setattr(fact_approved, 'is_vacancy', closest_plan_approved.is_vacancy)
                    if closest_plan_approved and not fact_approved.closest_plan_approved_id:
                        fact_approved.closest_plan_approved = closest_plan_approved
                    if fact_approved.type.has_details and not fact_approved.worker_day_details.exists():
                        self._create_wd_details(self.dt, fact_approved, active_user_empl, closest_plan_approved)
                    fact_approved.save()
                    self._create_or_update_not_approved_fact(fact_approved)
                else:
                    if self.type == self.TYPE_LEAVING:
                        prev_fa_wd = base_fact_approved_qs.filter(
                            fact_approved_extra_q,
                            employee_id=self.employee_id,
                            dt__lt=self.dt,
                            is_fact=True,
                            is_approved=True,
                        ).order_by('-is_equal_shops', '-is_closest_plan_approved_equal', '-dt').first()

                        # Если предыдущая смена начата и с момента открытия предыдущей смены прошло менее макс. длины смены,
                        # то обновляем время окончания предыдущей смены. (условие в closest_plan_approved_q)
                        if prev_fa_wd:
                            self.fact_wd = prev_fa_wd
                            if prev_fa_wd.last_edited_by_id:
                                return res

                            setattr(prev_fa_wd, self.TYPE_2_DTTM_FIELD[self.type], self.dttm)
                            setattr(prev_fa_wd, 'type_id',
                                    closest_plan_approved.type_id if closest_plan_approved else WorkerDay.TYPE_WORKDAY)
                            setattr(prev_fa_wd, 'shop_id', self.shop_id)
                            setattr(prev_fa_wd, 'last_edited_by', None)
                            setattr(prev_fa_wd, 'created_by', None)
                            if not prev_fa_wd.is_vacancy and closest_plan_approved:
                                setattr(prev_fa_wd, 'is_vacancy', closest_plan_approved.is_vacancy)
                            if closest_plan_approved and not prev_fa_wd.closest_plan_approved_id:
                                prev_fa_wd.closest_plan_approved = closest_plan_approved
                            prev_fa_wd.save()
                            # логично дату предыдущую ставить, так как это значение в отчетах используется
                            self.dt = prev_fa_wd.dt
                            super(AttendanceRecords, self).save(update_fields=['dt',])
                            self._create_or_update_not_approved_fact(prev_fa_wd)
                            return res

                        if self.shop.network.skip_leaving_tick:
                            return res

                    is_vacancy = WorkerDay.is_worker_day_vacancy(
                        active_user_empl.shop_id,
                        self.shop_id,
                        active_user_empl.main_work_type_id,
                        getattr(closest_plan_approved, 'worker_day_details_list', []),
                        is_vacancy=getattr(closest_plan_approved, 'is_vacancy', False),
                    )
                    fact_approved, _wd_created = WorkerDay.objects.update_or_create(
                        dt=self.dt,
                        employee_id=self.employee_id,
                        is_fact=True,
                        is_approved=True,
                        closest_plan_approved=closest_plan_approved,
                        defaults={
                            'shop_id': self.shop_id,
                            'employment': active_user_empl,
                            'type_id': closest_plan_approved.type_id if closest_plan_approved else WorkerDay.TYPE_WORKDAY,
                            self.TYPE_2_DTTM_FIELD[self.type]: self.dttm,
                            'is_vacancy': is_vacancy,
                            'source': WorkerDay.RECALC_FACT_FROM_ATT_RECORDS if recalc_fact_from_att_records else WorkerDay.SOURCE_AUTO_FACT,
                            # TODO: пока не стал проставлять is_outsource, т.к. придется делать доп. действие в интерфейсе,
                            # чтобы посмотреть что за сотрудник при правке факта из отдела аутсорс-клиента
                            # 'is_outsource': active_user_empl.shop.network_id != self.shop.network_id,
                        }
                    )
                    self.fact_wd = fact_approved
                    if fact_approved.type.has_details and (
                            _wd_created or not fact_approved.worker_day_details.exists()):
                        self._create_wd_details(self.dt, fact_approved, active_user_empl, closest_plan_approved)
                    if _wd_created:
                        if not closest_plan_approved:
                            transaction.on_commit(lambda: event_signal.send(
                                sender=None,
                                network_id=self.user.network_id,
                                event_code=EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN,
                                context={
                                    'user': {
                                        'last_name': self.user.last_name,
                                        'first_name': self.user.first_name,
                                    },
                                    'dttm': self.dttm.strftime('%Y-%m-%d %H:%M:%S'),
                                    'shop_id': self.shop_id,
                                },
                            ))
                    self._create_or_update_not_approved_fact(fact_approved)

        return res


class ExchangeSettings(AbstractModel):
    network = models.ForeignKey(Network, on_delete=models.PROTECT, null=True)
    default_constraints = {
        'second_day_before': 40,
        'second_day_after': 32,
        'first_day_after': 32,
        'first_day_before': 40,
        '1day_before': 40,
        '1day_after': 40,
    }

    # Создаем ли автоматически вакансии
    automatic_create_vacancies = models.BooleanField(default=False, verbose_name=_('Automatic create vacancies'))
    # Удаляем ли автоматически вакансии
    automatic_delete_vacancies = models.BooleanField(default=False, verbose_name=_('Automatic delete vacancies'))
    # Период, за который проверяем
    automatic_check_lack_timegap = models.DurationField(default=datetime.timedelta(days=7), verbose_name=_('Automatic check lack timegap'))
    #с какого дня выводить с выходного
    automatic_holiday_worker_select_timegap = models.DurationField(default=datetime.timedelta(days=8), verbose_name=_('Automatic holiday worker select timegap'))
    #включать ли автоматическую биржу смен
    automatic_exchange = models.BooleanField(default=False, verbose_name=_('Automatic exchange'))
    #максимальное количество рабочих часов в месяц для вывода с выходного
    max_working_hours = models.IntegerField(default=192, verbose_name=_('Max working hours'))

    constraints = models.CharField(max_length=250, default=json.dumps(default_constraints), verbose_name=_('Constraints'))
    exclude_positions = models.ManyToManyField('base.WorkerPosition', blank=True, verbose_name=_('Exclude positions'))
    # Минимальная потребность в сотруднике при создании вакансии
    automatic_create_vacancy_lack_min = models.FloatField(default=.5, verbose_name=_('Automatic create vacancy lack min'))
    # Максимальная потребность в сотруднике для удалении вакансии
    automatic_delete_vacancy_lack_max = models.FloatField(default=0.3, verbose_name=_('Automatic delete vacancy lack max'))

    # Только автоназначение сотрудников
    automatic_worker_select_timegap = models.DurationField(default=datetime.timedelta(days=1), verbose_name=_('Automatic worker select timegap'))
    #период за который делаем обмен сменами
    automatic_worker_select_timegap_to = models.DurationField(default=datetime.timedelta(days=2), verbose_name=_('Automatic worker select timegap to'))
    # Дробное число, на какую долю сотрудник не занят, чтобы совершить обмен
    automatic_worker_select_overflow_min = models.FloatField(default=0.8, verbose_name=_('Automatic worker select overflow min'))

    # Длина смены
    working_shift_min_hours = models.DurationField(default=datetime.timedelta(hours=4), verbose_name=_('Working shift min hours')) # Минимальная длина смены
    working_shift_max_hours = models.DurationField(default=datetime.timedelta(hours=12), verbose_name=_('Working shift max hours')) # Максимальная длина смены

    # Расстояние до родителя, в поддереве которого ищем сотрудников для автоназначения
    automatic_worker_select_tree_level = models.IntegerField(default=1, verbose_name=_('Automatic worker select tree level'))

    # Аутсорс компании, которым можно будет откликаться на автоматически созданную вакансию
    outsources = models.ManyToManyField(Network, verbose_name=_('Outsourcing companies'), blank=True,
        help_text=_('Outsourcing companies that will be able to respond to an automatically created vacancy'), related_name='client_exchange_settings')


class VacancyBlackList(models.Model):

    class Meta:
        unique_together = ('shop', 'symbol',)

    shop = models.ForeignKey(Shop, on_delete=models.CASCADE)
    symbol = models.CharField(max_length=128)

    def get_department(self):
        return self.shop


class WorkerDayPermission(AbstractModel):
    PLAN = 'P'
    FACT = 'F'

    GRAPH_TYPES = (
        (PLAN, _('Plan')),
        (FACT, _('Fact')),
    )

    # изменение типа дня в существующем дне считается как 2 действия: создание нового типа и удаление старого типа.
    CREATE = 'C'  # создание нового дня с каким-то типом
    UPDATE = 'U'  # изменение каких-то значений дня без изменения его типа
    DELETE = 'D'  # удаление какого-то типа дня
    APPROVE = 'A'

    ACTIONS = (
        (CREATE, _('Create')),
        (UPDATE, _('Change')),
        # Remove, т.к. Delete почему-то переводится в "Удалено", даже если в django.py "Удаление".
        (DELETE, _('Remove')),
        (APPROVE, _('Approve')),
    )
    ACTIONS_DICT = dict(ACTIONS)

    action = models.CharField(choices=ACTIONS, max_length=4, verbose_name='Действие')
    graph_type = models.CharField(choices=GRAPH_TYPES, max_length=1, verbose_name='Тип графика')
    wd_type = models.ForeignKey('timetable.WorkerDayType', verbose_name='Тип дня', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Разрешение для рабочего дня'
        verbose_name_plural = 'Разрешения для рабочего дня'
        unique_together = ('action', 'graph_type', 'wd_type')
        ordering = ('action', 'graph_type', 'wd_type')

    def __str__(self):
        return f'{self.get_action_display()} {self.get_graph_type_display()} {self.wd_type.name}'


class GroupWorkerDayPermission(AbstractModel):
    MY_SHOPS_ANY_EMPLOYEE = 1
    SUBORDINATE_EMPLOYEE = 2
    OUTSOURCE_NETWORK_EMPLOYEE = 3
    MY_NETWORK_EMPLOYEE = 4

    EMPLOYEE_TYPE_CHOICES = (
        (MY_SHOPS_ANY_EMPLOYEE, _('My shops employees')),  # с трудоустройством в моем магазине
        (SUBORDINATE_EMPLOYEE, _('Subordinate employees')),  # с трудоустройством в моем магазине
        (OUTSOURCE_NETWORK_EMPLOYEE, _('Outsource network employees')),  # без трудоустройства в моем магазине и из сети, аутсорсящей сеть пользователя, соверщающего действие
        (MY_NETWORK_EMPLOYEE, _('My network employees')),
    )
    EMPLOYEE_TYPE_CHOICES_REVERSED_DICT = {v: k for k, v in dict(EMPLOYEE_TYPE_CHOICES).items()}

    MY_SHOPS = 1
    MY_NETWORK_SHOPS = 2
    OUTSOURCE_NETWORK_SHOPS = 3
    CLIENT_NETWORK_SHOPS = 4

    SHOP_TYPE_CHOICES = (
        (MY_SHOPS, _('My shops')),
        (MY_NETWORK_SHOPS, _('My network shops')),
        (OUTSOURCE_NETWORK_SHOPS, _('Outsource network shops')),
        (CLIENT_NETWORK_SHOPS, _('Client network shops')),
    )
    SHOP_TYPE_CHOICES_REVERSED_DICT = {v: k for k, v in dict(SHOP_TYPE_CHOICES).items()}

    group = models.ForeignKey('base.Group', on_delete=models.CASCADE, verbose_name='Группа доступа')
    worker_day_permission = models.ForeignKey(
        'timetable.WorkerDayPermission', on_delete=models.CASCADE, verbose_name='Разрешение для рабочего дня')
    limit_days_in_past = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Ограничение на дни в прошлом',
        help_text='Если null - нет ограничений, если n - можно выполнять действие только n последних дней',
    )
    limit_days_in_future = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name='Ограничение на дни в будущем',
        help_text='Если null - нет ограничений, если n - можно выполнять действие только n будущих дней',
    )
    allow_actions_on_vacancies = models.BooleanField(
        verbose_name=_('Allow actions on vacancies'),
        default=True,
        help_text=_('Вакансией в данном случае является день, если он был явно создан как вакансия, '
                  'либо если магазин в трудоустройстве не совпадает с магазином выхода '
                  '(актуально для рабочий типов дней)'),
    )
    # need_closest_plan_approved = models.BooleanField(  # TODO: нужно?
    #     verbose_name='Нужен ближайший план',
    #     default=False, help_text='Актуально для создания, *изменения??? фактических записей')
    employee_type = models.PositiveSmallIntegerField(
        verbose_name='Тип сотрудника', default=SUBORDINATE_EMPLOYEE, choices=EMPLOYEE_TYPE_CHOICES)
    shop_type = models.PositiveSmallIntegerField(
        verbose_name='Тип магазина', help_text='Актуально только для рабочих типов дней',
        default=MY_NETWORK_SHOPS, choices=SHOP_TYPE_CHOICES,
    )

    class Meta:
        verbose_name = 'Разрешение группы для рабочего дня'
        verbose_name_plural = 'Разрешения группы для рабочего дня'
        unique_together = ('group', 'worker_day_permission', 'employee_type', 'shop_type')

    def __str__(self):
        return f'{self.group.name} {self.worker_day_permission}'

    @classmethod
    def get_perms_qs(cls, user, action, graph_type, wd_type_id, wd_dt, shop_id=None, is_vacancy=None):
        kwargs = {}
        if is_vacancy:
            kwargs['allow_actions_on_vacancies'] = True
        return cls.objects.filter(
            group__in=user.get_group_ids(shop_id=shop_id),
            worker_day_permission__action=action,
            worker_day_permission__graph_type=graph_type,
            worker_day_permission__wd_type_id=wd_type_id,
            **kwargs,
        )


class PlanAndFactHoursAbstract(models.Model):
    id = models.CharField(max_length=256, primary_key=True)
    dt = models.DateField()
    shop = models.ForeignKey('base.Shop', on_delete=models.DO_NOTHING)
    shop_name = models.CharField(max_length=512)
    shop_code = models.CharField(max_length=512)
    worker = models.ForeignKey('base.User', on_delete=models.DO_NOTHING)
    employee = models.ForeignKey('base.Employee', on_delete=models.DO_NOTHING)
    tabel_code = models.CharField(max_length=64)
    wd_type = models.ForeignKey('timetable.WorkerDayType', on_delete=models.DO_NOTHING)
    worker_fio = models.CharField(max_length=512)
    fact_work_hours = models.DecimalField(max_digits=4, decimal_places=2)
    plan_work_hours = models.DecimalField(max_digits=4, decimal_places=2)
    fact_manual_work_hours = models.DecimalField(max_digits=4, decimal_places=2)
    late_arrival_hours = models.DecimalField(max_digits=4, decimal_places=2)
    early_departure_hours = models.DecimalField(max_digits=4, decimal_places=2)
    early_arrival_hours = models.DecimalField(max_digits=4, decimal_places=2)
    late_departure_hours = models.DecimalField(max_digits=4, decimal_places=2)
    fact_without_plan_work_hours = models.DecimalField(max_digits=4, decimal_places=2)
    lost_work_hours = models.DecimalField(max_digits=4, decimal_places=2)
    late_arrival_count = models.PositiveSmallIntegerField()
    early_departure_count = models.PositiveSmallIntegerField()
    early_arrival_count = models.PositiveSmallIntegerField()
    late_departure_count = models.PositiveSmallIntegerField()
    fact_without_plan_count = models.PositiveSmallIntegerField()
    lost_work_hours_count = models.PositiveSmallIntegerField()
    is_vacancy = models.BooleanField()
    ticks_fact_count = models.PositiveSmallIntegerField()
    ticks_plan_count = models.PositiveSmallIntegerField()
    ticks_comming_fact_count = models.PositiveSmallIntegerField()
    ticks_leaving_fact_count = models.PositiveSmallIntegerField()
    worker_username = models.CharField(max_length=512)
    work_type_name = models.CharField(max_length=512)
    dttm_work_start_plan = models.DateTimeField()
    dttm_work_end_plan = models.DateTimeField()
    dttm_work_start_fact = models.DateTimeField()
    dttm_work_end_fact = models.DateTimeField()
    is_outsource = models.BooleanField()
    user_network = models.CharField(max_length=512)

    class Meta:
        abstract = True

    @property
    def dt_as_str(self):
        from src.util.models_converter import Converter
        return Converter.convert_date(self.dt)

    @property
    def tm_work_start_plan_str(self):
        return str(self.dttm_work_start_plan.time()) if self.dttm_work_start_plan else ''

    @property
    def tm_work_end_plan_str(self):
        return str(self.dttm_work_end_plan.time()) if self.dttm_work_end_plan else ''

    @property
    def tm_work_start_fact_str(self):
        return str(self.dttm_work_start_fact.time()) if self.dttm_work_start_fact else ''

    @property
    def tm_work_end_fact_str(self):
        return str(self.dttm_work_end_fact.time()) if self.dttm_work_end_fact else ''

    @property
    def plan_work_hours_timedelta(self):
        return datetime.timedelta(seconds=int(self.plan_work_hours * 60 * 60))

    @property
    def fact_work_hours_timedelta(self):
        return datetime.timedelta(seconds=int(self.fact_work_hours * 60 * 60))



class PlanAndFactHours(PlanAndFactHoursAbstract):
    class Meta:
        managed = False
        db_table = 'timetable_plan_and_fact_hours'


class ProdCal(models.Model):
    id = models.CharField(max_length=256, primary_key=True)
    dt = models.DateField()
    shop = models.ForeignKey('base.Shop', on_delete=models.DO_NOTHING)
    user = models.ForeignKey('base.User', on_delete=models.DO_NOTHING)
    employee = models.ForeignKey('base.Employee', on_delete=models.DO_NOTHING)
    employment = models.ForeignKey('base.Employment', on_delete=models.DO_NOTHING)
    norm_hours = models.FloatField()
    region = models.ForeignKey('base.Region', on_delete=models.DO_NOTHING)

    class Meta:
        managed = False
        db_table = 'prod_cal'


class ScheduleDeviations(PlanAndFactHoursAbstract):
    class Meta:
        managed = False
        db_table = 'timetable_schedule_deviations'
    
    employment_shop = models.ForeignKey('base.Shop', on_delete=models.DO_NOTHING, related_name='employment_shops')
    position = models.ForeignKey('base.WorkerPosition', on_delete=models.DO_NOTHING)
    employment_shop_name = models.CharField(max_length=512)
    position_name = models.CharField(max_length=512)
