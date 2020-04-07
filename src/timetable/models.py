from django.db import models
from django.contrib.auth.models import (
    UserManager
)

import datetime

from fcm_django.models import FCMDevice
from src.conf.djconfig import IS_PUSH_ACTIVE

from src.base.models import Shop, Employment, User

from src.base.models_abstract import AbstractModel, AbstractActiveModel, AbstractActiveNamedModel, AbstractActiveModelManager
from django.utils import timezone


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
            models.Q(dttm_added__date__lte=dt_from) | models.Q(dttm_added__isnull=True)
        ).filter(
            models.Q(dttm_deleted__date__gte=dt_to) | models.Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)
    
    def qos_delete(self, *args, **kwargs):
        for obj in self.filter(*args, **kwargs):
            obj.delete()


class WorkTypeName(AbstractActiveNamedModel):
    class Meta:
        verbose_name = 'Название типа работ'
        verbose_name_plural = 'Названия типов работ'

    def delete(self):
        super(WorkTypeName, self).delete()
        WorkType.objects.qos_delete(work_type_name__id=self.pk)
        return self


class WorkType(AbstractActiveModel):
    class Meta:
        verbose_name = 'Тип работ'
        verbose_name_plural = 'Типы работ'
        unique_together = ['shop', 'work_type_name']

    def __str__(self):
        return '{}, {}, {}, {}'.format(self.work_type_name.name, self.shop.name, self.shop.parent.name, self.id)

    id = models.BigAutoField(primary_key=True)

    priority = models.PositiveIntegerField(default=100)  # 1--главная касса, 2--линия, 3--экспресс
    dttm_last_update_queue = models.DateTimeField(null=True, blank=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT)
    work_type_name = models.ForeignKey(WorkTypeName, on_delete=models.PROTECT)
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


class Slot(AbstractActiveNamedModel):
    class Meta:
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
            models.Q(dttm_added__date__lte=dt_from) | models.Q(dttm_added__isnull=True)
        ).filter(
            models.Q(dttm_deleted__date__gt=dt_to) | models.Q(dttm_deleted__isnull=True)
        ).filter(*args, **kwargs)


class Cashbox(AbstractActiveNamedModel):
    class Meta:
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


class WorkerWorkType(AbstractModel):
    class Meta(object):
        verbose_name = 'Информация по сотруднику-типу работ'
        unique_together = (('employment', 'work_type'),)

    def __str__(self):
        return '{}, {}, {}'.format(self.employment.user.last_name, self.work_type.name, self.id)

    id = models.BigAutoField(primary_key=True)

    employment = models.ForeignKey(Employment, on_delete=models.PROTECT, related_name="work_types")
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
        return '{} {}, {}, {}, {}'.format(self.worker.last_name, self.worker.id, self.weekday, self.tm, self.id)

    id = models.BigAutoField(primary_key=True)
    shop = models.ForeignKey(Shop, blank=True, null=True, on_delete=models.PROTECT, related_name='worker_constraints')
    employment = models.ForeignKey(Employment, on_delete=models.PROTECT, null=True, related_name='worker_constraints')

    worker = models.ForeignKey(User, on_delete=models.PROTECT)
    weekday = models.SmallIntegerField()  # 0 - monday, 6 - sunday
    is_lite = models.BooleanField(default=False)  # True -- если сам сотрудник выставил, False -- если менеджер
    tm = models.TimeField()
    def get_department(self):
        return self.employment.shop


class WorkerDayManager(models.Manager):
    def qos_current_version(self, approved_only=False):
        if approved_only:
            return super().get_queryset().filter(
                models.Q(child__id__isnull=True) | models.Q(child__worker_day_approve=False),
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

    @staticmethod
    def qos_get_current_worker_day(worker_day):
        while True:
            current_worker_day = worker_day
            try:
                worker_day = worker_day.child
            except WorkerDay.child.RelatedObjectDoesNotExist:
                break
        return current_worker_day


class WorkerDay(AbstractModel):
    class Meta:
        verbose_name = 'Рабочий день сотрудника'
        verbose_name_plural = 'Рабочие дни сотрудников'
    
    TYPE_HOLIDAY = 'H'
    TYPE_WORKDAY = 'W'
    TYPE_VACATION = 'V'
    TYPE_SICK = 'S'
    TYPE_QUALIFICATION = 'Q'
    TYPE_ABSENSE = 'A'
    TYPE_MATERNITY = 'M'
    TYPE_BUSINESS_TRIP = 'T'

    TYPE_ETC = 'O'
    TYPE_DELETED = 'D'
    TYPE_EMPTY = 'E'

    TYPE_HOLIDAY_WORK = 'HW'
    TYPE_REAL_ABSENCE = 'RA'
    TYPE_EXTRA_VACATION = 'EV'
    TYPE_TRAIN_VACATION = 'TV'
    TYPE_SELF_VACATION = 'SV'
    TYPE_SELF_VACATION_TRUE = 'ST'
    TYPE_GOVERNMENT = 'G'
    TYPE_HOLIDAY_SPECIAL = 'HS'

    TYPE_MATERNITY_CARE = 'MC'
    TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE = 'C'

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
        (TYPE_DELETED, 'Удален'),
        (TYPE_EMPTY, 'Пусто'),
        (TYPE_HOLIDAY_WORK, 'Работа в выходной день'),
        (TYPE_REAL_ABSENCE, 'Прогул на основании акта'),
        (TYPE_EXTRA_VACATION, 'Доп. отпуск'),
        (TYPE_TRAIN_VACATION, 'Учебный отпуск'),
        (TYPE_SELF_VACATION, 'Отпуск за свой счёт'),
        (TYPE_SELF_VACATION_TRUE, 'Отпуск за свой счёт по уважительной причине'),
        (TYPE_GOVERNMENT, 'Гос. обязанности'),
        (TYPE_HOLIDAY_SPECIAL, 'Спец. выходной'),
        (TYPE_MATERNITY_CARE, 'Отпуск по уходу за ребёнком до 3-х лет'),
        (TYPE_DONOR_OR_CARE_FOR_DISABLED_PEOPLE, 'Выходные дни по уходу'),
    ]

    TYPES_PAID = [
        TYPE_WORKDAY,
        TYPE_QUALIFICATION,
        TYPE_BUSINESS_TRIP,
        TYPE_HOLIDAY_WORK,
        TYPE_EXTRA_VACATION,
        TYPE_TRAIN_VACATION,
    ]

    def __str__(self):
        return '{}, {}, {}, {}, {}, {}'.format(
            self.worker.last_name,
            self.shop.name if self.shop else '',
            self.shop.parent.name if self.shop and self.shop.parent else '',
            self.dt,
            self.type,
            self.id
        )

    def __repr__(self):
        return self.__str__()

    id = models.BigAutoField(primary_key=True)
    shop = models.ForeignKey(Shop, on_delete=models.PROTECT, null=True)
    employment = models.ForeignKey(Employment, on_delete=models.PROTECT, null=True)

    dt = models.DateField()  # todo: make immutable
    dttm_work_start = models.DateTimeField(null=True, blank=True)
    dttm_work_end = models.DateTimeField(null=True, blank=True)

    worker = models.ForeignKey(User, on_delete=models.PROTECT)  # todo: make immutable
    type = models.CharField(choices=TYPES, max_length=2, default=TYPE_EMPTY)

    work_types = models.ManyToManyField(WorkType, through='WorkerDayCashboxDetails')

    is_approved = models.BooleanField(default=False)
    created_by = models.ForeignKey(User, on_delete=models.PROTECT, blank=True, null=True, related_name='user_created')

    comment = models.TextField(null=True, blank=True)
    parent_worker_day = models.ForeignKey('self', on_delete=models.PROTECT, blank=True, null=True, related_name='child')
    work_hours = models.DurationField(default=datetime.timedelta(days=0))

    is_fact = models.BooleanField(default=False) # плановое или фактическое расписание
    dttm_added = models.DateTimeField(default=timezone.now)

    objects = WorkerDayManager()

    @classmethod
    def is_type_with_tm_range(cls, t):
        return t in (cls.TYPE_WORKDAY, cls.TYPE_BUSINESS_TRIP, cls.TYPE_QUALIFICATION)

    @staticmethod
    def count_work_hours(break_triplets, dttm_work_start, dttm_work_end):
        work_hours = int((dttm_work_end - dttm_work_start).total_seconds()) / 60
        for break_triplet in break_triplets:
            if work_hours >= break_triplet[0] and work_hours <= break_triplet[1]:
                work_hours = work_hours - sum(break_triplet[2])
                break
        return round(work_hours / 60)

    def get_department(self):
        return self.shop

    def save(self, *args, **kwargs):
        if self.dttm_work_end and self.dttm_work_start:
            self.work_hours = self.dttm_work_end - self.dttm_work_start
        else:
            self.work_hours = datetime.timedelta(0)
        super().save(*args, **kwargs)


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

    TYPE_WORK = 'W'
    TYPE_WORK_TRADING_FLOOR = 'Z'
    TYPE_BREAK = 'B'
    TYPE_STUDY = 'S'
    TYPE_VACANCY = 'V'
    TYPE_SOON = 'C'
    TYPE_FINISH = 'H'
    TYPE_ABSENCE = 'A'
    TYPE_DELETED = 'D'

    DETAILS_TYPES = (
            (TYPE_WORK, 'work period'),
            (TYPE_BREAK, 'rest / break'),
            (TYPE_STUDY, 'study period'),
            (TYPE_VACANCY, 'vacancy'),
            (TYPE_WORK_TRADING_FLOOR, 'work in trading floor'),
    )

    TYPE_T = 'T'

    WORK_TYPES_LIST = (
        TYPE_WORK,
        TYPE_STUDY,
        TYPE_WORK_TRADING_FLOOR,
    )

    DETAILS_TYPES_LIST = (
        TYPE_WORK,
        TYPE_BREAK,
        TYPE_STUDY,
        TYPE_WORK_TRADING_FLOOR,
    )

    id = models.BigAutoField(primary_key=True)

    worker_day = models.ForeignKey(WorkerDay, on_delete=models.CASCADE, null=True, blank=True, related_name='worker_day_details')
    on_cashbox = models.ForeignKey(Cashbox, on_delete=models.PROTECT, null=True, blank=True)
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT, null=True, blank=True)

    status = models.CharField(max_length=1, choices=DETAILS_TYPES, default=TYPE_WORK)
    is_vacancy = models.BooleanField(default=False)

    is_tablet = models.BooleanField(default=False)

    dttm_from = models.DateTimeField()
    dttm_to = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return '{}, {}, {}, {}, {}-{}, id: {}'.format(
            # self.worker_day.worker.last_name,
            self.dttm_from.date(),
            '', '',
            self.work_type.work_type_name.name if self.work_type else None,
            self.dttm_from.replace(microsecond=0).time() if self.dttm_from else self.dttm_from,
            self.dttm_to.replace(microsecond=0).time() if self.dttm_to else self.dttm_to,
            self.id,
        )

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

    workerday_details = models.ForeignKey(WorkerDayCashboxDetails, null=True, blank=True, on_delete=models.PROTECT)

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
                                       models.Q(dttm_from__gte=vacancy.dttm_from, dttm_from__lt=vacancy.dttm_to) |
                                       models.Q(dttm_to__gt=vacancy.dttm_from, dttm_to__lte=vacancy.dttm_to) |
                                       models.Q(dttm_from__lte=vacancy.dttm_from, dttm_to__gte=vacancy.dttm_to),
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


class Timetable(AbstractModel):
    class Meta(object):
        unique_together = (('shop', 'dt'),)
        verbose_name = 'Расписание'
        verbose_name_plural = 'Расписания'

    READY = 'R'
    PROCESSING = 'P'
    ERROR = 'E'

    STATUS = [
        (READY, 'Готово'),
        (PROCESSING, 'В процессе'),
        (ERROR, 'Ошибка')
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
    status = models.CharField(choices=STATUS, default=PROCESSING, max_length=1)
    dttm_status_change = models.DateTimeField()

    # statistics
    fot = models.IntegerField(default=0, blank=True, null=True)
    lack = models.SmallIntegerField(default=0, blank=True, null=True)
    idle = models.SmallIntegerField(default=0, blank=True, null=True)
    workers_amount = models.IntegerField(default=0, blank=True, null=True)
    revenue = models.IntegerField(default=0, blank=True, null=True)
    fot_revenue = models.IntegerField(default=0, blank=True, null=True)

    task_id = models.CharField(max_length=256, null=True, blank=True)


class AttendanceRecords(AbstractModel):
    class Meta(object):
        verbose_name = 'Данные УРВ'

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

    dttm = models.DateTimeField()
    type = models.CharField(max_length=1, choices=RECORD_TYPES)
    user = models.ForeignKey(User, on_delete=models.PROTECT)
    verified = models.BooleanField(default=True)

    shop = models.ForeignKey(Shop, on_delete=models.PROTECT) # todo: or should be to shop? fucking logic

    def __str__(self):
        return 'UserId: {}, type: {}, dttm: {}'.format(self.user_id, self.type, self.dttm)

    def save(self, *args, **kwargs):
        """
        Создание WorkerDay при занесении отметок.

        """
        super(AttendanceRecords, self).save(*args, **kwargs)

        type2dtfield = {
            self.TYPE_COMING: 'dttm_work_start',
            self.TYPE_LEAVING: 'dttm_work_end'
        }

        worker_days = WorkerDay.objects.filter(
            shop=self.shop,
            worker=self.user,
            dt=self.dttm.date(),
        )
        wdays = {}
        if len(worker_days) > 4:
            raise ValueError( f"Worker {self.user} has too many worker days on {self.dttm.date()}")

        for wd in worker_days:
            key_fact = 'fact' if wd.is_fact else 'plan'
            key_approved = 'approved' if wd.is_approved else 'not_approved'
            if not key_fact in wdays:
                wdays[key_fact] = {}
            wdays[key_fact][key_approved] = wd

        if 'fact' in wdays and 'approved' in wdays['fact']:
            setattr(wdays['fact']['approved'], type2dtfield[self.type], self.dttm)
            wdays['fact']['approved'].save()
        else:
            wd = WorkerDay(
                shop=self.shop,
                worker=self.user,
                dt=self.dttm.date(),
                is_fact=True,
                is_approved=True
            )
            setattr(wd, type2dtfield[self.type], self.dttm)

            if 'plan' in wdays:
                wd.parent_worker_day = wdays['plan']['approved'] \
                    if 'approved' in wdays['plan']\
                    else wdays['plan']['not_approved']

            wd.save()

            if 'fact' in wdays and 'not_approved' in wdays['fact']:
                wdays['fact']['not_approved'].parent_worker_day = wd
                wdays['fact']['not_approved'].save()


class ExchangeSettings(AbstractModel):
    # Создаем ли автоматически вакансии
    automatic_check_lack = models.BooleanField(default=False)
    # Период, за который проверяем
    automatic_check_lack_timegap = models.DurationField(default=datetime.timedelta(days=7))

    # Минимальная потребность в сотруднике при создании вакансии
    automatic_create_vacancy_lack_min = models.FloatField(default=.5)
    # Максимальная потребность в сотруднике для удалении вакансии
    automatic_delete_vacancy_lack_max = models.FloatField(default=0.3)

    # Только автоназначение сотрудников
    automatic_worker_select_timegap = models.DurationField(default=datetime.timedelta(days=1))
    # Дробное число, на какую долю сотрудник не занят, чтобы совершить обмен
    automatic_worker_select_overflow_min = models.FloatField(default=0.8)

    # Длина смены
    working_shift_min_hours = models.DurationField(default=datetime.timedelta(hours=4)) # Минимальная длина смены
    working_shift_max_hours = models.DurationField(default=datetime.timedelta(hours=12)) # Максимальная длина смены

    # Расстояние до родителя, в поддереве которого ищем сотрудников для автоназначения
    automatic_worker_select_tree_level = models.IntegerField(default=1)

