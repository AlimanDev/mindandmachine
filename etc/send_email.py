from django.core.mail import EmailMessage
from src.conf.djconfig import ADMINS


def send_email(message, to_email, file=None):
    '''
    Функция-обёртка для отправки email сообщения (в том числе файла)
    :param message: сообщение
    :param to_email: email на который отправляем сообщение
    :param file: файл
    :return:
    '''
    result = EmailMessage(
        subject='Сообщение от mind&machine',
        body=message,
        from_email=ADMINS[0][1],
        to=[to_email],
    )
    if file:
        result.attach_file(file)
    result = result.send()
    return 'Сообщение {}'.format('отправлено' if result else 'неотправлено')
