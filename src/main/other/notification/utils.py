
from django.utils.timezone import now
from django.db.models.query import QuerySet
from datetime import timedelta
from fcm_django.models import FCMDevice
from src.timetable.models import (
    WorkerDay,
)

work_types = {
    WorkerDay.TYPE_WORKDAY: 'рабочий день',
    WorkerDay.TYPE_ABSENSE: 'отсутствие',
    WorkerDay.TYPE_HOLIDAY: 'выходной',
    WorkerDay.TYPE_VACATION: 'отпуск',
}


# def get_month_name(dt):
#     """
#     Функция которая возвращает название месяца в зависимости от полученной даты
#
#     Args:
#         dt(datetime.date): дата
#
#     Returns:
#         (char): название месяца
#     """
#     return month_dict[dt.month]


def create_notification(action, instance, requester=None):
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

    # todo: rewrite
    pass

    # notification_text = None
    # notification_type = Notifications.TYPE_INFO
    #
    # if action is 'C':
    #     if isinstance(instance, User):
    #         notification_text = 'Пользователь {} {} присоединился к команде!'.format(instance.first_name,
    #                                                                                  instance.last_name)
    #     elif isinstance(instance, Cashbox):
    #         notification_text = 'На тип {} была добавлена касса с номером {}.'.format(instance.type.name,
    #                                                                                   instance.number)
    #     elif isinstance(instance, WorkType):
    #         notification_text = 'Был добавлен тип работ {}.'.format(instance.name)
    #     elif isinstance(instance, Timetable):
    #         if instance.status == Timetable.PROCESSING:
    #             notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' начало составляться.'
    #         elif instance.status == Timetable.READY:
    #             notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' составлено.'
    #             notification_type = Notifications.TYPE_SUCCESS
    #         elif instance.status == Timetable.ERROR:
    #             notification_text = 'Ошибка при составлении расписания на ' + get_month_name(instance.dt) + '.'
    #             notification_type = Notifications.TYPE_ERROR
    #
    #     elif isinstance(instance, WorkerDayChangeRequest):
    #         change_request_info = ''
    #         if instance.type == WorkerDay.TYPE_WORKDAY:
    #             change_request_info = ' с {} по {}'.format(
    #                 instance.dttm_work_start.strftime('%H:%M'),
    #                 instance.dttm_work_end.strftime('%H:%M')
    #             )
    #         if len(instance.wish_text) > 0:
    #             change_request_info += '. Текст пожелания: ' + instance.wish_text
    #         notification_text = 'Пользователь {} {} запросил изменение рабочего дня на {}: {}'.format(
    #             instance.worker.first_name if not requester else requester.first_name,
    #             instance.worker.last_name if not requester else requester.last_name,
    #             instance.dt.strftime('%d.%m.%Y'),
    #             work_types[instance.type]
    #         ) + change_request_info
    #
    # elif action is 'D':
    #     if isinstance(instance, User) and instance.dt_fired:
    #         notification_text = 'Пользователь {} {} был удален.'.format(instance.first_name, instance.last_name)
    #     elif isinstance(instance, Cashbox) and instance.dttm_deleted:
    #         notification_text = 'Касса с номером {} была удалена с типа {}.'.format(instance.number, instance.type.name)
    #     elif isinstance(instance, WorkType) and instance.dttm_deleted:
    #         notification_text = 'Тип работ {} был удален.'.format(instance.name)
    #     elif isinstance(instance, Timetable):
    #         notification_text = 'Расписание на ' + get_month_name(instance.dt) + ' было успешно удалено.'
    #
    # return notification_text, notification_type


def send_notification(action, instance, recipient_list=None, sender=None, mobile_note_header=None):
    """
    Функция "отправки" уведомлений (на самом деле она их просто создает в бд)

    Args:
        action(char): 'C' или 'D' для создания/удаления соответственно
        instance(object): объект модели о которой нам надо уведомить
        recipient_list(list): список получателей
        sender(user object): тот, кто тригернул это действие (обычно request.user)

    Returns:

    """

    # todo: rewrite with new logic (delete and use event mm_event_create)
    pass

    # notification_text, notification_type = create_notification(action, instance, requester=sender)
    # additional_args = {}
    # if isinstance(instance, Cashbox):
    #     shop_id = instance.type.shop.id
    # elif isinstance(instance, WorkerDayChangeRequest):
    #     shop_id = instance.worker.shop.id
    #     additional_args['object_id'] = instance.id
    #     additional_args['content_type'] = ContentType.objects.get(model=WorkerDayChangeRequest.__name__.lower())
    # else:
    #     shop_id = instance.shop.id
    #
    # if recipient_list is None:
    #     recipient_list = User.objects.filter(
    #         function_group__allowed_functions__access_type__in=FunctionGroup.__INSIDE_SHOP_TYPES__,
    #         shop_id=shop_id
    #     )
    #
    # elif not isinstance(recipient_list, list) and not isinstance(recipient_list, QuerySet):
    #     recipient_list = [recipient_list]
    #
    # # todo: refactor 100500 query
    # for recipient in recipient_list:
    #     if not Notifications.objects.filter(
    #         type=notification_type,
    #         to_worker=recipient,
    #         text=notification_text,
    #         dttm_added__lt=now() + timedelta(hours=2, minutes=30)
    #         # нет смысла слать уведомления больше чем раз в полчаса
    #     ):
    #         created_note = Notifications.objects.create(
    #             type=notification_type,
    #             to_worker=recipient,
    #             text=notification_text,
    #             **additional_args
    #         )
    #         device_to_send = FCMDevice.objects.filter(user_id=recipient.id).first()
    #         if device_to_send:
    #             device_to_send.send_message(
    #                 title=mobile_note_header,
    #                 body=notification_text
    #             )
    #         if sender and sender == recipient:
    #             created_note.was_read = True
    #             created_note.save()
