from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from src.conf.djconfig import DEFAULT_FROM_EMAIL, COMPANY_NAME


def send_email(template_name, to, subject, context, request=None):
    msg = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string(template_name, context=context, request=request),
        from_email=DEFAULT_FROM_EMAIL,
        to=to if isinstance(to, list) else [to],
        headers={'X-Campaign-Id': COMPANY_NAME}
    )
    msg.send()
