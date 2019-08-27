from src.db.models import Notifications
from src.util.utils import api_method, JsonResponse
from src.util.models_converter import NotificationConverter
from .forms import SetNotificationsReadForm, GetNotificationsForm, NotifyAction
from django.db.models import Q

@api_method('GET', GetNotificationsForm, check_permissions=False)
def get_notifications(request, form):
    """
    Получить список уведомлений

    Args:
        method: GET
        url: /api/other/notifications/get_notifications
        pointer(int): required = False. Начиная с каких уведомлений получать (id меньше pointer'a)
        count(int): required = True. Сколько уведомлений мы хотим получить

    Returns:
        {
            | "get_noty_pointer": int,
            | 'get_new_noty_pointer': id уведомления начиная с которого в след раз получать,
            'notifications': [
                | 'was_read': True/False,
                | 'id': id уведомления,
                | 'to_worker': id пользователя кому это уведомления,
                | 'type': "I"/"W"/etc,
                | 'dttm_added': дата создания уведомления
            | ],
            | 'unread_count': количество непрочитанных уведомлений

        }
    """
    pointer = form.get('pointer')
    count = form['count']
    user = request.user

    old_notifications = Notifications.objects.mm_filter(to_worker=user, was_read=True).order_by('-id')

    if pointer is not None:
        old_notifications = old_notifications.filter(id__lt=pointer)
    old_notifications = list(old_notifications[:count])

    result = dict(
        get_noty_pointer=old_notifications[-1].id if (
                    len(old_notifications) > 0 and len(old_notifications) == count) else None,
        old_notifications=[NotificationConverter.convert(notification) for notification in old_notifications]
    )

    if pointer is None:
        result['get_new_noty_pointer'] = old_notifications[0].id if len(old_notifications) > 0 else -1
        # result['unread_count'] = Notifications.objects.filter(to_worker=user, was_read=False).count()
    result['new_notifications'] = [
        NotificationConverter.convert(note) for note in Notifications.objects.mm_filter(to_worker=user, was_read=False)
    ]

    return JsonResponse.success(result)


@api_method('GET', GetNotificationsForm, check_permissions=False)
def get_notifications2(request, form):
    """
    Получить список уведомлений

    Args:
        method: GET
        url: /api/other/notifications/get_notifications
        pointer(int): required = False. Начиная с каких уведомлений получать (id меньше pointer'a)
        count(int): required = True. Сколько уведомлений мы хотим получить
        type(str): required = False. Тип уведомления (vacancy - вакансия, other - остальные) default = all.

    Returns:
        {
            | "next_noty_pointer": int or null if no more,
            | 'get_new_noty_pointer': id уведомления начиная с которого в след раз получать,
            'notifications': [
                | 'was_read': True/False,
                | 'id': id уведомления,
                | 'to_worker': id пользователя кому это уведомления,
                | 'type': "I"/"W"/etc,
                | 'dttm_added': дата создания уведомления
                | 'text': текст сообщения,
                | 'object_id': id связанной с уведомлением сущности
                | '
            | ],
            | 'unread_count': количество непрочитанных уведомлений
        }
    """

    pointer = form.get('pointer')
    count = form.get('count')
    if pointer is None:
        pointer = 0
    if count is None:
        count = 20

    notifies = Notifications.objects.mm_filter(
        Q(event__workerday_details__dttm_deleted__isnull=True) |
        Q(event__workerday_details__worker_day__worker=request.user),
        to_worker=request.user).order_by('-id')

    if form['type'] == 'vacancy':
        notifies = list(notifies.filter(
            event__workerday_details__isnull=False)[pointer * count: (pointer + 1) * count])
    elif form['type'] == 'other':
        notifies = list(notifies.filter(
            event__workerday_details__isnull=True)[pointer * count: (pointer + 1) * count])
    else:
        notifies = list(notifies[pointer * count: (pointer + 1) * count])

    result = {
        'unread_count': Notifications.objects.filter(to_worker=request.user, was_read=False).count(),
        'next_noty_pointer': pointer + 1 if len(notifies) == count else None,
        'notifications': [NotificationConverter.convert(note) for note in notifies],
    }
    return JsonResponse.success(result)


@api_method('POST', SetNotificationsReadForm, check_permissions=False)
def set_notifications_read(request, form):
    """
    Сделать уведомление прочитанным

    Args:
        method: POST
        url: /api/other/notifications/set_notifications_read
        ids(list): список уведомлений, которые сделать прочитанными (либо [] -- для всех)
        set_all(bool): если True, то все не прочитанные становятся прочитанными
    Returns:
        {
            'updated_count': количество прочтенных уведомлений
        }
    """

    extra_kwargs = {}
    if not form.get('set_all'):
        extra_kwargs = {
            'id__in': form['ids'],
        }

    count = Notifications.objects.filter(to_worker=request.user, **extra_kwargs).update(was_read=True)
    return JsonResponse.success({
        'updated_count': count
    })


@api_method('POST', NotifyAction, check_permissions=False)
def do_notify_action(request, form):
    """
    Уведомление с каким-то предложением / подтверждением и пользователь дает согласие через эту функцию

    method: POST
    url: /api/other/notifications/do_notify_action
    Args:
        notify_id(int): ID уведомления

    Returns: {}
    """

    notify = Notifications.objects.mm_filter(
        id=form['notify_id'],
        to_worker=request.user,
    ).first()

    if notify:
        event = notify.event

        result = event.do_action(request.user)
        if result['status'] == 0:
            return JsonResponse.success()
    else:
        result = {'text': 'Невозможно выполнить действие'}
    return JsonResponse.value_error(result['text'])
