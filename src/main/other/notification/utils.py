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
    """
    Функция которая возвращает название месяца в зависимости от полученной даты

    Args:
        dt(datetime.date): дата

    Returns:
        (char): название месяца
    """
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
    Создает текст и тип уведомления в зависимости от действия и объекта

    Args:
        action(str): 'C' или 'D' для создания/удаления соответственно
        instance(object): объект какой-то модели

    Returns:
        (tuple): tuple содержащий:
            notification_text(char): текст уведоления
            notification_type(Notifications.type): тип уведомления
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
    Функция "отправки" уведомлений (на самом деле она их просто создает в бд)

    Args:
        action(char): 'C' или 'D' для создания/удаления соответственно
        instance(object): объект модели о которой нам надо уведомить
        recipient_list(list): список получателей
        sender(user object): тот, кто тригернул это действие (обычно request.user)

    Returns:

    """
    notification_text, notification_type = create_notification(action, instance)

    shop_id = instance.type.shop.id if isinstance(instance, Cashbox) else instance.shop.id
    print(shop_id)
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
