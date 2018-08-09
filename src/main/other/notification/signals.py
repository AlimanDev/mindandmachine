from django.db.models.signals import post_save
from django.dispatch import receiver
from src.db.models import (
    Timetable,
    User,
    Notifications,
    CashboxType,
    Cashbox
)
from .utils import (
    send_notification,
    get_month_name
)


@receiver(post_save, sender=Timetable)
def timetable_status_note(instance, created=False, **kwargs):
    """
    creates notifications after timetable is ready/ timetable started to generate
    :param instance:
    :param created:
    :param kwargs:
    :return:
    """
    shop_id = instance.shop.id
    managers_dir_list = User.objects.filter(shop_id=shop_id, work_type=User.WorkType.TYPE_MANAGER.value)
    # todo: аналогично tasks.py
    if created:
        notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' начало составляться.'
        send_notification(managers_dir_list, notification_text, Notifications.TYPE_INFO)
    else:
        if instance.status == Timetable.Status.READY.value:
            notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' составлено.'
            send_notification(managers_dir_list, notification_text, Notifications.TYPE_SUCCESS)
        elif instance.status == Timetable.Status.ERROR.value:
            notification_text = 'Ошибка при составлении расписания на ' + get_month_name(instance.dt) + '.'
            send_notification(managers_dir_list, notification_text, Notifications.TYPE_ERROR)


@receiver(post_save, sender=User)
@receiver(post_save, sender=CashboxType)
@receiver(post_save, sender=Cashbox)
def notification_user_cashbox_create_delete(instance, created=False, **kwargs):
    """
    creates notification if user/cashbox/cashobox_type was created/"deleted"
    :param instance:
    :param created:
    :param kwargs:
    :return:
    """
    shop_id = instance.type.shop.id if isinstance(instance, Cashbox) else instance.shop.id
    managers_dir_list = User.objects.filter(shop_id=shop_id, work_type=User.WorkType.TYPE_MANAGER.value)
    notification_text = None
    # todo: аналогично
    if created:
        if isinstance(instance, User):
            notification_text = 'Пользователь {} {} присоединился к команде!'.format(instance.first_name, instance.last_name)
        elif isinstance(instance, Cashbox):
            notification_text = 'На тип {} была добавлена касса с номером {}.'.format(instance.type.name, instance.number)
        elif isinstance(instance, CashboxType):
            notification_text = 'Был добавлен тип касс {}.'.format(instance.name)
    else:
        if isinstance(instance, User) and instance.dt_fired:
            notification_text = 'Пользователь {} {} был удален.'.format(instance.first_name, instance.last_name)
        elif isinstance(instance, Cashbox) and instance.dttm_deleted:
            notification_text = 'Касса с номером {} была удалена с типа {}.'.format(instance.number, instance.type.name)
        elif isinstance(instance, CashboxType) and instance.dttm_deleted:
            notification_text = 'Тип касс {} был удален.'.format(instance.name)

    if notification_text:
        send_notification(managers_dir_list, notification_text, Notifications.TYPE_INFO)
