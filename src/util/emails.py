from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from src.conf.djconfig import EMAIL_HOST_USER


def send_email(template_name, to, subject, context, request=None):
    msg = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(template_name, context=context, request=request),
        from_email=EMAIL_HOST_USER,
        to=to if isinstance(to, list) else [to],
    )
    msg.send()
