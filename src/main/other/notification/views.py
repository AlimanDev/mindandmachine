from src.db.models import Notifications
from src.util.utils import api_method, JsonResponse
from src.util.models_converter import NotificationConverter
from.forms import SetNotificationsReadForm, GetNotificationsForm


@api_method('GET', GetNotificationsForm, check_permissions=False)
def get_notifications(request, form):
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
    count = Notifications.objects.filter(to_worker=request.user, id__in=form['ids']).update(was_read=True)
    return JsonResponse.success({
        'updated_count': count
    })
