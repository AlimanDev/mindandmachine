"""
General-purpose email module.
`send_email` works as the `django.core.email.send_email`, adding a header to track statistics through Sendsay SMTP server.
`prepare_message_...` functions to form message body.
"""

from .sending import send_email
from .messages import prepare_message_tick_report
