from django.core.mail import EmailMessage
from src.conf.djconfig import ADMINS
from src.db.models import User


def send_email(message, to_email, file=None):
    '''
        Функция-обёртка для отправки email сообщения (в том числе файла)
        :param message: сообщение
        :param to_email: email на который отправляем сообщение
        :param file: файл
        :return:
        '''
    result = EmailMessage(
        subject='Тема сообщения',
        body=message,
        from_email=ADMINS[0][1],
        to=[to_email],
    )
    if file:
        result.attach_file(file)
    result = result.send()
    return 'Сообщение {}'.format('отправлено' if result else 'неотправлено')


# Для celery
def send_notify_email(message, id_list, file=None):
    '''
    Функция-обёртка для отправки email сообщений (в том числе файлов)
    :param message: сообщение
    :param id_list: список id пользователей
    :param file: файл
    :return:
    '''
    user_emails = [user.email for user in User.objects.filter(id__in=id_list)]
    result = EmailMessage(
        subject='Тема сообщения',
        body=message,
        from_email=ADMINS[0][1],
        to=user_emails,
    )
    if file:
        result.attach_file(message)
    result = result.send()
    return 'Отправлено {} сообщений из {}'.format(result, len(id_list))

