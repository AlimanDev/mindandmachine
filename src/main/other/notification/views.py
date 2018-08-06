from src.db.models import Notifications
from src.util.utils import api_method, JsonResponse
from src.util.models_converter import NotificationConverter
from.forms import SetNotificationsReadForm


@api_method('GET')
def get_notifications(request):
    user = request.user

    notifications = Notifications.objects.filter(to_worker=user).order_by('-id').unread()
    result = []

    for notification in notifications:
        result.append({
            'dttm': NotificationConverter.convert_datetime(notification.dttm_added),
            'notification': NotificationConverter.convert(notification)
            })

    return JsonResponse.success(result)


@api_method('POST', SetNotificationsReadForm)
def set_notifications_read(request, form):
    count = Notifications.objects.filter(user=request.user, id__in=form['ids']).update(was_read=True)
    return JsonResponse.success({
        'updated_count': count
    })
