from django.core import mail

from src.conf.djconfig import COMPANY_NAME


def send_email(*args, **kwargs):
    'All-purpose email sender. Sets a header for email statistics.'
    kwargs.setdefault('headers', {}).setdefault('X-Campaign-Id', COMPANY_NAME)
    fail_silently = kwargs.pop('fail_silently', False)
    message = mail.EmailMessage(*args, **kwargs)
    return message.send(fail_silently)
