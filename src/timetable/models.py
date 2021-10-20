import datetime
import json
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import (
    UserManager
)
from django.db import models
from django.db import transaction
from django.db.models import (
    Subquery, OuterRef, Max, Q, Case, When, Value, FloatField, F, IntegerField, Exists, BooleanField, Min
)
from django.db.models import UniqueConstraint
from django.db.models.functions import Abs, Cast, Extract, Least
from django.db.models.query import QuerySet
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from model_utils import FieldTracker
from rest_framework.exceptions import ValidationError

from src.base.models import Shop, Employment, User, Event, Network, Break, ProductionDay, Employee
from src.base.models_abstract import AbstractModel, AbstractActiveModel, AbstractActiveNetworkSpecificCodeNamedModel, \
    AbstractActiveModelManager
from src.events.signals import event_signal
from src.recognition.events import EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN
from src.tasks.models import Task
from src.timetable.exceptions import (
    WorkTimeOverlap,
    WorkDayTaskViolation,
    MultipleWDTypesOnOneDateForOneEmployee,
    HasAnotherWdayOnDate,
)
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
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Название типа работ'
        verbose_name_plural = 'Названия типов работ'

    def delete(self):
        super(WorkTypeName, self).delete()
        WorkType.objects.qos_delete(work_type_name__id=self.pk)
        return self

    def __str__(self):
        return 'id: {}, name: {}, code: {}'.format(
            self.id,
            self.name,
            self.code,
        )


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
        if hasattr(self, 'code'):
            self.work_type_name = WorkTypeName.objects.get(code=self.code)
        super(WorkType, self).save(*args, **kwargs)

    def get_department(self):
        return self.shop

    def delete(self):
        if Cashbox.objects.filter(type_id=self.id, dttm_deleted__isnull=True).exists():
            raise models.ProtectedError('There is cashboxes with such work_type', Cashbox.objects.filter(type_id=self.id, dttm_deleted__isnull=True))

        super(WorkType, self).delete()
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


class CashboxManager(models.Manager):
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
            Q(dttm_added__date__lte=dt_from) | Q(dttm_added__isnull=True)
        ).filter(
            Q(dttm_deleted__date__gt=dt_to) | Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)


class Cashbox(AbstractActiveNetworkSpecificCodeNamedModel):
    class Meta(AbstractActiveNetworkSpecificCodeNamedModel.Meta):
        verbose_name = 'Рабочее место '
        verbose_name_plural = 'Рабочие места'

    def __str__(self):
        return '{}, {}, {}, {}, {}'.format(
            self.type.work_type_name.name,
            self.type.shop.name,
            self.type.shop.parent.name,
            self.id,
            self.name
        )

    id = models.BigAutoField(primary_key=True)

    type = models.ForeignKey(WorkType, on_delete=models.PROTECT)
    name = models.CharField(max_length=128)
    code = models.CharField(max_length=64, default='', blank=True)
    bio = models.CharField(max_length=512, default='', blank=True)
    objects = CashboxManager()


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
                work_hours__gte=datetime.timedelta(0),
            ).exclude(
                type_id=WorkerDay.TYPE_EMPTY,
            ))
        ).filter(
            Q(is_fact=True) |
            Q(type__is_dayoff=True, is_fact=False, has_fact_approved_on_dt=False),
            is_approved=True,
            *args,
            **kwargs,
        )


class WorkerDayManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().exclude(
            type__is_dayoff=False, employment_id__isnull=True, employee_id__isnull=False)

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
    ordering = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

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
        return {wdt.code: wdt for wdt in cls.objects.all()}


class WorkerDay(AbstractModel):
    """
    Ключевая сущность, которая определяет, что делает сотрудник в определенный момент времени (работает, на выходном и тд)

    Что именно делает сотрудник в выбранный день определяет поле type. При этом, если сотрудник работает в этот день, то
    у него должен быть указан магазин (shop). Во всех остальных случаях shop_id должно быть пустым (aa: fixme WorkerDaySerializer)

    """
    class Meta:
        verbose_name = 'Рабочий день сотрудника'
        verbose_name_plural = 'Рабочие дни сотрудников'
        constraints = (
            UniqueConstraint(
                fields=['dt', 'employee', 'is_fact', 'is_approved'],
                # TODO: нельзя делать ограничения по джоинам, как быть?
                #   пока захардкодил коды для типов, которые есть или будут is_dayoff=False
                condition=~Q(type_id__in=['W', 'Q', 'T', 'SD', 'R']),
                name='unique_dt_employee_is_fact_is_approved_if_not_workday'
            ),
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
    def _enrich_create_or_update_perms_data(cls, create_or_update_perms_data, obj_dict):
        action = WorkerDayPermission.CREATE_OR_UPDATE
        graph_type = WorkerDayPermission.FACT if obj_dict.get('is_fact') else WorkerDayPermission.PLAN
        wd_type_id = obj_dict.get('type_id')
        dt = obj_dict.get('dt')
        shop_id = obj_dict.get('shop_id')
        k = f'{graph_type}_{action}_{wd_type_id}_{shop_id}'
        create_or_update_perms_data.setdefault(k, set()).add(dt)

    @classmethod
    def _get_check_batch_perms_extra_kwargs(cls):
        return {
            'wd_types_dict': WorkerDayType.get_wd_types_dict(),
        }

    @classmethod
    def _check_batch_delete_qs_perms(cls, user, delete_qs, **kwargs):
        from src.timetable.worker_day.utils import check_worker_day_permissions
        from src.timetable.worker_day.views import WorkerDayViewSet
        action = WorkerDayPermission.DELETE
        grouped_qs =  delete_qs.values(
            'is_fact',
            'type_id',
            'shop_id',
        ).annotate(
            dt_min=Min('dt'),
            dt_max=Min('dt'),
        ).values_list(
            'is_fact',
            'type_id',
            'shop_id',
            'dt_min',
            'dt_max',
        ).distinct()
        for is_fact, wd_type_id, shop_id, dt_min, dt_max in grouped_qs:
            check_worker_day_permissions(
                user=user,
                shop_id=shop_id,
                action=action,
                graph_type=WorkerDayPermission.FACT if is_fact else WorkerDayPermission.PLAN,
                wd_types=[wd_type_id],
                dt_from=dt_min,
                dt_to=dt_max,
                error_messages=WorkerDayViewSet.error_messages,
                wd_types_dict=kwargs.get('wd_types_dict'),
            )

    @classmethod
    def _check_create_or_update_perms(cls, user, create_or_update_perms_data, **kwargs):
        from src.timetable.worker_day.utils import check_worker_day_permissions
        from src.timetable.worker_day.views import WorkerDayViewSet
        for k, dates_set in create_or_update_perms_data.items():
            graph_type, action, wd_type_id, shop_id = k.split('_')
            if shop_id == 'None':
                shop_id = None
            check_worker_day_permissions(
                user=user,
                shop_id=shop_id,
                action=action,
                graph_type=graph_type,
                wd_types=[wd_type_id],
                dt_from=min(dates_set),
                dt_to=max(dates_set),
                error_messages=WorkerDayViewSet.error_messages,
                wd_types_dict=kwargs.get('wd_types_dict'),
            )

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
        return {
            'dttm_work_start_tabel',
            'dttm_work_end_tabel',
            'work_hours',
        }

    def calc_day_and_night_work_hours(self):
        from src.util.models_converter import Converter
        # TODO: нужно учитывать работу в праздничные дни? -- сейчас is_celebration в ProductionDay всегда False

        if self.type.is_dayoff:
            return 0.0, 0.0, 0.0

        if self.work_hours > datetime.timedelta(0):
            work_seconds = self.work_hours.seconds
        else:
            return 0.0, 0.0, 0.0

        work_start = self.dttm_work_start_tabel or self.dttm_work_start
        work_end = self.dttm_work_end_tabel or self.dttm_work_end
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

        if work_start.time() > night_edges[0] or work_start.time() < night_edges[1]:
            tm_start = _time_to_float(work_start.time())
        else:
            tm_start = _time_to_float(night_edges[0])
        if work_end.time() > night_edges[0] or work_end.time() < night_edges[1]:
            tm_end = _time_to_float(work_end.time())
        else:
            tm_end = _time_to_float(night_edges[1])

        night_seconds = (tm_end - tm_start if tm_end > tm_start else 24 - (tm_start - tm_end)) * 60 * 60
        total_seconds = (work_end - work_start).total_seconds()

        break_time_seconds = total_seconds - work_seconds

        break_time_half_seconds = break_time_seconds / 2
        if night_seconds > break_time_half_seconds:
            work_hours_day = round(
                (total_seconds - night_seconds - break_time_half_seconds) / 3600, 2)
            work_hours_night = round((night_seconds - break_time_half_seconds) / 3600, 2)
        else:
            substract_from_day_seconds = break_time_half_seconds - night_seconds
            work_hours_night = 0.0
            work_hours_day = round(
                (total_seconds - substract_from_day_seconds - break_time_half_seconds) / 3600, 2)
        work_hours = work_hours_day + work_hours_night
        return work_hours, work_hours_day, work_hours_night

    def _calc_wh(self):
        position_break_triplet_cond = self.employment and self.employment.position and self.employment.position.breaks
        if self.dttm_work_end and self.dttm_work_start and self.shop and (
                self.shop.settings or position_break_triplet_cond or self.shop.network.breaks):
            breaks = self.employment.position.breaks.breaks if position_break_triplet_cond else self.shop.settings.breaks.breaks if self.shop.settings else self.shop.network.breaks.breaks
            dttm_work_start = _dttm_work_start = self.dttm_work_start
            dttm_work_end = _dttm_work_end = self.dttm_work_end
            if self.shop.network.crop_work_hours_by_shop_schedule and self.crop_work_hours_by_shop_schedule:
                from src.util.models_converter import Converter
                dt = Converter.parse_date(self.dt) if isinstance(self.dt, str) else self.dt
                shop_schedule = self.shop.get_schedule(dt=dt)
                if shop_schedule is None:
                    return dttm_work_start, dttm_work_end, datetime.timedelta(0)

                open_at_0 = all(getattr(shop_schedule['tm_open'], a) == 0 for a in ['hour', 'second', 'minute'])
                close_at_0 = all(getattr(shop_schedule['tm_close'], a) == 0 for a in ['hour', 'second', 'minute'])
                shop_24h_open = open_at_0 and close_at_0

                if not shop_24h_open:
                    dttm_shop_open = datetime.datetime.combine(dt, shop_schedule['tm_open'])
                    if self.dttm_work_start < dttm_shop_open:
                        dttm_work_start = dttm_shop_open

                    dttm_shop_close = datetime.datetime.combine(
                        (dt + datetime.timedelta(days=1)) if close_at_0 else dt, shop_schedule['tm_close'])
                    if self.dttm_work_end > dttm_shop_close:
                        dttm_work_end = dttm_shop_close
            break_time = None
            fine = 0
            if self.is_fact:
                plan_approved = None
                if self.closest_plan_approved_id:
                    plan_approved = WorkerDay.objects.filter(id=self.closest_plan_approved_id).first()
                if plan_approved:
                    fine = self.get_fine(
                        _dttm_work_start,
                        _dttm_work_end,
                        plan_approved.dttm_work_start,
                        plan_approved.dttm_work_end,
                        self.employment.position.wp_fines if self.employment and self.employment.position else None,
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
                        # учитываем перерыв плана, если факт получился больше
                        fact_hours = self.count_work_hours(breaks, dttm_work_start, dttm_work_end)
                        plan_hours = plan_approved.work_hours
                        if fact_hours > plan_hours:
                            work_hours = (plan_approved.dttm_work_end - plan_approved.dttm_work_start).total_seconds() / 60
                            for break_triplet in breaks:
                                if work_hours >= break_triplet[0] and work_hours <= break_triplet[1]:
                                    break_time = sum(break_triplet[2])
                                    break
                    else:
                        return dttm_work_start, dttm_work_end, datetime.timedelta(0)

            return dttm_work_start, dttm_work_end, self.count_work_hours(breaks, dttm_work_start, dttm_work_end, break_time=break_time, fine=fine)

        return self.dttm_work_start, self.dttm_work_end, datetime.timedelta(0)

    def __init__(self, *args, need_count_wh=False, **kwargs):
        super().__init__(*args, **kwargs)
        if need_count_wh:
            self.dttm_work_start_tabel, self.dttm_work_end_tabel, self.work_hours = self._calc_wh()

    id = models.BigAutoField(primary_key=True, db_index=True)
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

    objects = WorkerDayManager.from_queryset(WorkerDayQuerySet)()  # исключает раб. дни у которых employment_id is null
    objects_with_excluded = models.Manager.from_queryset(WorkerDayQuerySet)()

    tracker = FieldTracker(fields=('work_hours',))

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
    def count_work_hours(break_triplets, dttm_work_start, dttm_work_end, break_time=None, fine=0):
        work_hours = ((dttm_work_end - dttm_work_start).total_seconds() / 60) - fine
        if break_time:
            work_hours = work_hours - break_time
            return datetime.timedelta(minutes=work_hours)
        for break_triplet in break_triplets:
            if work_hours >= break_triplet[0] and work_hours <= break_triplet[1]:
                work_hours = work_hours - sum(break_triplet[2])
                break

        if work_hours < 0:
            return datetime.timedelta(0)

        return datetime.timedelta(minutes=work_hours)

    @staticmethod
    def get_fine(dttm_work_start, dttm_work_end, dttm_work_start_plan, dttm_work_end_plan, fines):
        fine = 0
        if dttm_work_start_plan and dttm_work_end_plan and fines:
            arrive_fines = fines.get('arrive_fines', [])
            departure_fines = fines.get('departure_fines', [])
            arrive_timedelta = (dttm_work_start - dttm_work_start_plan).total_seconds() / 60
            departure_timedelta = (dttm_work_end_plan - dttm_work_end).total_seconds() / 60
            for arrive_fine in arrive_fines:
                if arrive_timedelta >= arrive_fine[0] and arrive_timedelta <= arrive_fine[1]:
                    fine += arrive_fine[2]
                    break
            for departure_fine in departure_fines:
                if departure_timedelta >= departure_fine[0] and departure_timedelta <= departure_fine[1]:
                    fine += departure_fine[2]
                    break
        return fine

    def get_department(self):
        return self.shop

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

    @property
    def dt_as_str(self):
        from src.util.models_converter import Converter
        return Converter.convert_date(self.dt)

    @property
    def type_name(self):
        return self.get_type_display()

    def save(self, *args, **kwargs): # todo: aa: частая модель для сохранения, отправлять запросы при сохранении накладно
        self.dttm_work_start_tabel, self.dttm_work_end_tabel, self.work_hours = self._calc_wh()

        if self.last_edited_by_id is None:
            self.last_edited_by_id = self.created_by_id

        is_new = self.id is None

        res = super().save(*args, **kwargs)
        fines = self.employment.position.wp_fines if self.employment and self.employment.position else None

        # запускаем пересчет часов для факта, если изменились часы в подтвержденном плане
        if self.shop and (self.shop.network.only_fact_hours_that_in_approved_plan or fines) and \
                self.tracker.has_changed('work_hours') and \
                not self.type.is_dayoff and \
                self.is_plan and self.is_approved:
            fact_qs = WorkerDay.objects.filter(
                dt=self.dt,
                employee_id=self.employee_id,
                is_fact=True,
                type__is_dayoff=False
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

        return res

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
            has_overlap=Exists(
                WorkerDay.objects.filter(
                    ~Q(id=OuterRef('id')),
                    Q(
                        Q(dttm_work_end__lt=OuterRef('dttm_work_start')) &
                        Q(dttm_work_start__gte=OuterRef('dttm_work_start'))
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
                    ),
                    employee__user_id=OuterRef('employee__user_id'),
                    dt=OuterRef('dt'),
                    is_fact=OuterRef('is_fact'),
                    is_approved=OuterRef('is_approved'),
                )
            )
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
    def check_multiple_workday_types(cls, employee_days_q=None, employee_id=None, employee_id__in=None, user_id=None,
                                user_id__in=None, dt=None, dt__in=None, is_fact=None, is_approved=None, raise_exc=True,
                                exc_cls=None):
        """
        Проверка, что нету различных типов рабочих дней на 1 дату для 1 сотрудника
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

        has_multiple_workday_types_qs = cls.objects.filter(q).annotate(
            has_multiple_workday_types=Exists(
                WorkerDay.objects.filter(
                    ~Q(id=OuterRef('id')),
                    ~Q(type_id=OuterRef('type_id')),
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    is_fact=OuterRef('is_fact'),
                    is_approved=OuterRef('is_approved'),
                )
            )
        ).filter(
            has_multiple_workday_types=True,
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
    def get_closest_plan_approved_q(cls, employee_id, dt, dttm_work_start, dttm_work_end, delta_in_secs):
        return WorkerDay.objects.filter(
            Q(dttm_work_start__gte=dttm_work_start - datetime.timedelta(seconds=delta_in_secs)) &
            Q(dttm_work_start__lte=dttm_work_start + datetime.timedelta(seconds=delta_in_secs)),
            Q(dttm_work_end__gte=dttm_work_end - datetime.timedelta(seconds=delta_in_secs)) &
            Q(dttm_work_end__lte=dttm_work_end + datetime.timedelta(seconds=delta_in_secs)),
            employee_id=employee_id,
            dt=dt,
            is_fact=False,
            is_approved=True,
        )

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

            cls.objects.filter(
                q_obj, **filter_kwargs,
            ).update(
                closest_plan_approved=Subquery(cls.get_closest_plan_approved_q(
                    employee_id=OuterRef('employee_id'),
                    dt=OuterRef('dt'),
                    dttm_work_start=OuterRef('dttm_work_start'),
                    dttm_work_end=OuterRef('dttm_work_end'),
                    delta_in_secs=delta_in_secs,
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


class WorkerDayChangeRequest(AbstractActiveModel):
    class Meta(object):
        verbose_name = 'Запрос на изменения рабочего дня'
        unique_together = ('worker', 'dt')

    def __str__(self):
        return '{}, {}, {}'.format(self.worker.id, self.dt, self.status_type)

    TYPE_APPROVED = 'A'
    TYPE_DECLINED = 'D'
    TYPE_PENDING = 'P'

    STATUS_CHOICES = (
        (TYPE_APPROVED, 'Approved'),
        (TYPE_DECLINED, 'Declined'),
        (TYPE_PENDING, 'Pending'),
    )

    id = models.BigAutoField(primary_key=True)
    status_type = models.CharField(max_length=1, choices=STATUS_CHOICES, default=TYPE_PENDING)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    dt = models.DateField()
    type = models.CharField(choices=WorkerDay.TYPES, max_length=2, default=WorkerDay.TYPE_EMPTY)

    dttm_work_start = models.DateTimeField(null=True, blank=True)
    dttm_work_end = models.DateTimeField(null=True, blank=True)
    wish_text = models.CharField(null=True, blank=True, max_length=512)


class EventManager(models.Manager):
    def mm_event_create(self, users, push_title=None, **kwargs):
        event = self.create(**kwargs)

        # users = User.objects.filter(
        #     function_group__allowed_functions__func=noti_groups['func'],
        #     function_group__allowed_functions__access_type__in=noti_groups['access_types'],
        # )
        # if event.department:
        #     users = users.filter(shop=event.department)

        notis = Notifications.objects.bulk_create([Notifications(event=event, to_worker=u) for u in users])
        # todo: add sending push notifies
        if (not push_title is None) and IS_PUSH_ACTIVE:
            devices = FCMDevice.objects.filter(user__in=users)
            devices.send_message(title=push_title, body=event.text)
        return event


class Event(AbstractModel):
    dttm_added = models.DateTimeField(auto_now_add=True)

    text = models.CharField(max_length=256)
    # hidden_text = models.CharField(max_length=256, default='')

    department = models.ForeignKey(Shop, null=True, blank=True, on_delete=models.PROTECT) # todo: should be department model?

    workerday_details = models.ForeignKey(WorkerDayCashboxDetails, null=True, blank=True, on_delete=models.PROTECT, related_name='events')

    objects = EventManager()

    def get_text(self):
        if self.workerday_details:
            from src.util.models_converter import Converter

            if self.workerday_details.dttm_deleted:
                return 'Вакансия отмена'
            elif self.workerday_details.worker_day_id:
                return 'Вакансия на {} в {} уже выбрана.'.format(
                    Converter.convert_date(self.workerday_details.dttm_from.date()),
                    self.workerday_details.work_type.shop.name,
                )
            else:
                return 'Открыта вакансия на {} на {} в {}. Время работы: с {} по {}. Хотите выйти?'.format(
                    self.workerday_details.work_type.work_type_name.name,
                    Converter.convert_date(self.workerday_details.dttm_from.date()),
                    self.workerday_details.work_type.shop.name,
                    Converter.convert_time(self.workerday_details.dttm_from.time()),
                    Converter.convert_time(self.workerday_details.dttm_to.time()),
                )

        else:
            return self.text

    def is_question(self):
        return not self.workerday_details_id is None

    def do_action(self, user):
        res = {
            'status': 0,
            'text': '',
        }

        if self.workerday_details_id: # действие -- выход на вакансию
            vacancy = self.workerday_details
            user_worker_day = WorkerDay.objects.qos_current_version().filter(
                worker=user,
                dt=vacancy.dttm_from.date()
            ).first()

            if user_worker_day and vacancy:
                is_updated = False
                update_condition = user_worker_day.type != WorkerDay.TYPE_WORKDAY or \
                                   WorkerDayCashboxDetails.objects.filter(
                                       Q(dttm_from__gte=vacancy.dttm_from, dttm_from__lt=vacancy.dttm_to) |
                                       Q(dttm_to__gt=vacancy.dttm_from, dttm_to__lte=vacancy.dttm_to) |
                                       Q(dttm_from__lte=vacancy.dttm_from, dttm_to__gte=vacancy.dttm_to),
                                       worker_day_id=user_worker_day.id,
                                       dttm_deleted__isnull=True,
                                   ).count() == 0

                # todo: actually should be transaction (check condition and update)
                # todo: add time for go between shops
                if update_condition:
                    is_updated = WorkerDayCashboxDetails.objects.filter(
                        id=vacancy.id,
                        worker_day__isnull=True,
                        dttm_deleted__isnull=True,
                    ).update(
                        worker_day_id=user_worker_day.id,
                        status=WorkerDayCashboxDetails.TYPE_WORK,
                    )

                    if is_updated:
                        user_worker_day.type = WorkerDay.TYPE_WORKDAY

                        if (user_worker_day.dttm_work_start is None) or (user_worker_day.dttm_work_start > vacancy.dttm_from):
                            user_worker_day.dttm_work_start = vacancy.dttm_from

                        if (user_worker_day.dttm_work_end is None) or (user_worker_day.dttm_work_end < vacancy.dttm_to):
                            user_worker_day.dttm_work_end = vacancy.dttm_to

                        user_worker_day.save()

                    if not is_updated:
                        res['status'] = 3
                        res['text'] = 'Невозможно выполнить действие'

                else:
                    res['status'] = 4
                    res['text'] = 'Вы не можете выйти на эту смену'
            else:
                res['status'] = 2
                res['text'] = 'График на этот период еще не составлен'
        else:
            res['status'] = 1
            res['text'] = 'К этому уведомлению не может быть действия'
        return res

    def is_action_active(self):
        if self.workerday_details and (self.workerday_details.dttm_deleted is None) and (self.workerday_details.worker_day_id is None):
            return True
        return False


class NotificationManager(models.Manager):
    def mm_filter(self, *args, **kwargs):
        return self.filter(*args, **kwargs).select_related(
            'event',
            'event__workerday_details',
            'event__workerday_details__work_type',
            'event__workerday_details__work_type__shop'
        )


class Notifications(AbstractModel):
    class Meta(object):
        verbose_name = 'Уведомления'

    def __str__(self):
        return '{}, {}, {}, id: {}'.format(
            self.to_worker.last_name,
            self.shop.name if self.shop else 'no shop',
            self.dttm_added,
            # self.text[:60],
            self.id
        )

    id = models.BigAutoField(primary_key=True)
    shop = models.ForeignKey(Shop, null=True, on_delete=models.PROTECT, related_name='notifications')

    dttm_added = models.DateTimeField(auto_now_add=True)
    to_worker = models.ForeignKey(User, on_delete=models.PROTECT)

    was_read = models.BooleanField(default=False)
    event = models.ForeignKey(Event, on_delete=models.PROTECT, null=True)

    # text = models.CharField(max_length=512)
    # type = models.CharField(max_length=1, choices=TYPES, default=TYPE_SUCCESS)

    # content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE, blank=True, null=True)
    # object_id = models.PositiveIntegerField(blank=True, null=True)
    # object = GenericForeignKey(ct_field='content_type', fk_field='object_id')
    objects = NotificationManager()


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
            employment = closest_plan_approved.employment
            if not employment:
                raise ValidationError(_('You have no active employment'))
            dt = closest_plan_approved.dt

        return employee_id, employment, dt, record_type, closest_plan_approved

    def _create_wd_details(self, dt, fact_approved, active_user_empl, closest_plan_approved):
        if closest_plan_approved:
            if fact_approved.shop_id == closest_plan_approved.shop_id:
                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=fact_approved,
                            work_type_id=details.work_type_id,
                        )
                        for details in closest_plan_approved.worker_day_details.all()
                    ]
                )
            else:
                WorkerDayCashboxDetails.objects.bulk_create(
                    [
                        WorkerDayCashboxDetails(
                            work_part=details.work_part,
                            worker_day=fact_approved,
                            work_type=WorkType.objects.filter(
                                shop_id=fact_approved.shop_id,
                                work_type_name_id=details.work_type.work_type_name_id,
                            ).first(),
                        )
                        for details in closest_plan_approved.worker_day_details.select_related('work_type')
                    ]
                )
        elif active_user_empl:
            employment_work_type = EmploymentWorkType.objects.filter(
                employment=active_user_empl).order_by('-priority').first()
            if employment_work_type:
                WorkerDayCashboxDetails.objects.create(
                    work_part=1,
                    worker_day=fact_approved,
                    work_type_id=employment_work_type.work_type_id,
                )

    def _create_or_update_not_approved_fact(self, fact_approved):
        # TODO: попробовать найти вариант без удаления workerday?
        WorkerDay.objects.filter(
            dt=fact_approved.dt,
            employee_id=fact_approved.employee_id,
            is_fact=True,
            is_approved=False,
            last_edited_by__isnull=True,
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
                    )
                    WorkerDay.check_work_time_overlap(
                        employee_id=fact_approved.employee_id, dt=fact_approved.dt, is_fact=True)
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
        fact_approved_extra_q = Q(closest_plan_approved=closest_plan_approved)
        if self.type == self.TYPE_LEAVING:
            fact_approved_extra_q |= Q(
                dttm_work_start__isnull=False,
                diff_between_tick_and_work_start_seconds__lte=F('shop__network__max_work_shift_seconds'),
            )
        return fact_approved_extra_q

    def save(self, *args, recalc_fact_from_att_records=False, **kwargs):
        """
        Создание WorkerDay при занесении отметок.
        """
        employee_id, active_user_empl, dt, record_type, closest_plan_approved = self.get_day_data(
            self.dttm, self.user, self.shop, self.type)
        self.dt = dt
        self.type = self.type or record_type
        self.employee_id = self.employee_id or employee_id
        res = super(AttendanceRecords, self).save(*args, **kwargs)

        if self.type == self.TYPE_NO_TYPE:
            return res

        with transaction.atomic():
            base_fact_approved_qs = self._get_base_fact_approved_qs(closest_plan_approved, shop_id=self.shop_id)
            fact_approved_extra_q = self._get_fact_approved_extra_q(closest_plan_approved)
            fact_approved = base_fact_approved_qs.filter(
                fact_approved_extra_q,
                dt=self.dt,
                employee_id=self.employee_id,
                is_fact=True,
                is_approved=True,
            ).order_by('-is_equal_shops', '-is_closest_plan_approved_equal').first()

            if fact_approved:
                if fact_approved.last_edited_by_id and (
                        recalc_fact_from_att_records and not self.user.network.edit_manual_fact_on_recalc_fact_from_att_records):
                    return

                # если это отметка о приходе, то не перезаписываем время начала работы в графике
                # если время отметки больше, чем время начала работы в существующем графике
                skip_condition = (self.type == self.TYPE_COMING) and \
                                 fact_approved.dttm_work_start and self.dttm > fact_approved.dttm_work_start
                if skip_condition:
                    return

                setattr(fact_approved, self.TYPE_2_DTTM_FIELD[self.type], self.dttm)
                # TODO: проставление такого же типа как в плане? (тест + проверить)
                setattr(fact_approved, 'type_id',
                        closest_plan_approved.type_id if closest_plan_approved else WorkerDay.TYPE_WORKDAY)
                if not fact_approved.worker_day_details.exists():
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
                        setattr(prev_fa_wd, self.TYPE_2_DTTM_FIELD[self.type], self.dttm)
                        setattr(prev_fa_wd, 'type_id',
                                closest_plan_approved.type_id if closest_plan_approved else WorkerDay.TYPE_WORKDAY)
                        prev_fa_wd.save()
                        # логично дату предыдущую ставить, так как это значение в отчетах используется
                        self.dt = prev_fa_wd.dt
                        super(AttendanceRecords, self).save(update_fields=['dt',])
                        self._create_or_update_not_approved_fact(prev_fa_wd)
                        return

                    if self.shop.network.skip_leaving_tick:
                        return

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
                        'is_vacancy': active_user_empl.shop_id != self.shop_id if active_user_empl else False,
                        # TODO: пока не стал проставлять is_outsource, т.к. придется делать доп. действие в интерфейсе,
                        # чтобы посмотреть что за сотрудник при правке факта из отдела аутсорс-клиента
                        #'is_outsource': active_user_empl.shop.network_id != self.shop.network_id,
                    }
                )
                if _wd_created or not fact_approved.worker_day_details.exists():
                    self._create_wd_details(self.dt, fact_approved, active_user_empl, closest_plan_approved)
                if _wd_created:
                    if not closest_plan_approved:
                        transaction.on_commit(lambda: event_signal.send(
                            sender=None,
                            network_id=self.user.network_id,
                            event_code=EMPLOYEE_WORKING_NOT_ACCORDING_TO_PLAN,
                            context={
                                'director':{
                                    'email': self.shop.director.email if self.shop.director else self.shop.email,
                                    'name': self.shop.director.first_name if self.shop.director else self.shop.name, 
                                },
                                'user':{
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
        (PLAN, 'План'),
        (FACT, 'Факт'),
    )

    CREATE_OR_UPDATE = 'CU'
    DELETE = 'D'
    APPROVE = 'A'

    ACTIONS = (
        (CREATE_OR_UPDATE, _('Create/update')),
        # Remove, т.к. Delete почему-то переводится в "Удалено", даже если в django.py "Удаление".
        (DELETE, _('Remove')),
        (APPROVE, _('Approve')),
    )
    ACTIONS_DICT = dict(ACTIONS)

    action = models.CharField(choices=ACTIONS, max_length=2, verbose_name='Действие')
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

    class Meta:
        verbose_name = 'Разрешение группы для рабочего дня'
        verbose_name_plural = 'Разрешения группы для рабочего дня'
        unique_together = ('group', 'worker_day_permission',)

    def __str__(self):
        return f'{self.group.name} {self.worker_day_permission}'

    @classmethod
    def has_permission(cls, user, action, graph_type, wd_type, wd_dt):
        if isinstance(wd_dt, str):
            wd_dt = datetime.datetime.strptime(wd_dt, settings.QOS_DATE_FORMAT).date()
        # FIXME-devx: будет временной лаг из-за того, что USE_TZ=False, откуда брать таймзону? - из shop?
        today = (datetime.datetime.now() + datetime.timedelta(hours=3)).date()
        return cls.objects.filter(
            Q(limit_days_in_past__isnull=True) | Q(limit_days_in_past__gte=(today - wd_dt).days),
            Q(limit_days_in_future__isnull=True) | Q(limit_days_in_future__gte=(wd_dt - today).days),
            group__in=user.get_group_ids(),  # добавить shop ?
            worker_day_permission__action=action,
            worker_day_permission__graph_type=graph_type,
            worker_day_permission__wd_type=wd_type,
        ).exists()


class PlanAndFactHours(models.Model):
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
    late_arrival = models.PositiveSmallIntegerField()
    early_departure = models.PositiveSmallIntegerField()
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

    class Meta:
        managed = False
        db_table = 'timetable_plan_and_fact_hours'

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
