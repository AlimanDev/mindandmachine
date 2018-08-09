from src.db.models import Notifications
from django.utils.timezone import now
from datetime import timedelta


def send_notification(man_dir_list, notification_text, notification_type):
    for man_dir in man_dir_list:
        if not Notifications.objects.filter(
                type=notification_type,
                to_worker=man_dir,
                text=notification_text,
                dttm_added__lt=now() + timedelta(hours=2, minutes=30)  # нет смысла слать уведомления больше чем раз в полчаса
        ):
            Notifications.objects.create(
                type=notification_type,
                to_worker=man_dir,
                text=notification_text
            )


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



