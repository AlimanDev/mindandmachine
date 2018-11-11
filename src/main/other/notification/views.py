from src.db.models import Notifications
from src.util.utils import api_method, JsonResponse
from src.util.models_converter import NotificationConverter
from.forms import SetNotificationsReadForm, GetNotificationsForm


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
            | 'get_noty_pointer': int,
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

    notifications = Notifications.objects.filter(to_worker=user).order_by('-id')

    if pointer is not None:
        notifications = notifications.filter(id__lt=pointer)
    notifications = list(notifications[:count])

    result = {
        'get_noty_pointer': notifications[-1].id if len(notifications) > 0 else None,
        'notifications': [
            NotificationConverter.convert(notification) for notification in notifications
    ]}

    if pointer is None:
        result['get_new_noty_pointer'] = notifications[0].id if len(notifications) > 0 else -1
        result['unread_count'] = Notifications.objects.filter(to_worker=user, was_read=False).count()

    return JsonResponse.success(result)


@api_method('POST', SetNotificationsReadForm, check_permissions=False)
def set_notifications_read(request, form):
    """
    Сделать уведомление прочитанным

    Args:
        method: POST
        url: /api/other/notifications/set_notifications_read
        ids(list): список уведомлений, которые сделать прочитанными (либо [] -- для всех)

    Returns:
        {
            'updated_count': количество прочтенных уведомлений
        }
    """
    count = Notifications.objects.filter(to_worker=request.user, id__in=form['ids']).update(was_read=True)
    return JsonResponse.success({
        'updated_count': count
    })
