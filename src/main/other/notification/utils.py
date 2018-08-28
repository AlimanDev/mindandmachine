from src.db.models import Notifications
from django.utils.timezone import now
from datetime import timedelta
from src.db.models import (
    CashboxType,
    Cashbox,
    User,
    Timetable
)
from django.db.models import Q


def get_month_name(dt):
    month_dict = {
        1: 'январь',
        2: 'февраль',
        3: 'март',
        4: 'апрель',
        5: 'май',
        6: 'июнь',
        7: 'июль',
        8: 'август',
        9: 'сентябрь',
        10: 'октябрь',
        11: 'ноябрь',
        12: 'декабрь',
    }
    return month_dict[dt.month]


def create_notification(action, instance):
    """
    creates notification text and notification type for different situations
    :param instance: instance, about which we need to notify
    :param action: 'C' or 'D' for creation or deletion
    :return:
    """
    notification_text = None
    notification_type = Notifications.TYPE_INFO

    if action is 'C':
        if isinstance(instance, User):
            notification_text = 'Пользователь {} {} присоединился к команде!'.format(instance.first_name,
                                                                                     instance.last_name)
        elif isinstance(instance, Cashbox):
            notification_text = 'На тип {} была добавлена касса с номером {}.'.format(instance.type.name,
                                                                                      instance.number)
        elif isinstance(instance, CashboxType):
            notification_text = 'Был добавлен тип касс {}.'.format(instance.name)
        elif isinstance(instance, Timetable):
            if instance.status == Timetable.Status.PROCESSING.value:
                    notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' начало составляться.'
            elif instance.status == Timetable.Status.READY.value:
                notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' составлено.'
                notification_type = Notifications.TYPE_SUCCESS
            elif instance.status == Timetable.Status.ERROR.value:
                notification_text = 'Ошибка при составлении расписания на ' + get_month_name(instance.dt) + '.'
                notification_type = Notifications.TYPE_ERROR

    elif action is 'D':
        if isinstance(instance, User) and instance.dt_fired:
            notification_text = 'Пользователь {} {} был удален.'.format(instance.first_name, instance.last_name)
        elif isinstance(instance, Cashbox) and instance.dttm_deleted:
            notification_text = 'Касса с номером {} была удалена с типа {}.'.format(instance.number, instance.type.name)
        elif isinstance(instance, CashboxType) and instance.dttm_deleted:
            notification_text = 'Тип касс {} был удален.'.format(instance.name)
        elif isinstance(instance, Timetable):
            notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' было успешно удалено.'

    return notification_text, notification_type


def send_notification(action, instance, recipient_list=None, sender=None):
    """

    :param instance: instance, about which we need to notify
    :param action: 'C' or 'D' for creation or deletion
    :param recipient_list: list of users (or one user) who'd receive this notification
    :param sender: user who performed action of creation or deletion
    :return:
    """
    notification_text, notification_type = create_notification(action, instance)

    shop_id = instance.type.shop.id if isinstance(instance, Cashbox) else instance.shop.id
    if recipient_list is None:
        recipient_list = User.objects.filter(
            Q(group=User.GROUP_SUPERVISOR) | Q(group=User.GROUP_MANAGER),
            shop_id=shop_id
        )
    elif not isinstance(recipient_list, list):
        recipient_list = [recipient_list]
    for recipient in recipient_list:
        if not Notifications.objects.filter(
                type=notification_type,
                to_worker=recipient,
                text=notification_text,
                dttm_added__lt=now() + timedelta(hours=2, minutes=30)
                # нет смысла слать уведомления больше чем раз в полчаса
        ):
            created_note = Notifications.objects.create(
                type=notification_type,
                to_worker=recipient,
                text=notification_text,

            )
            if sender and sender == recipient:
                created_note.was_read = True
                created_note.save()
