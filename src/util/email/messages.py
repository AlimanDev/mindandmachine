from django.utils.translation import gettext as _


def prepare_message_tick_report(url: str):
    message = _('Your report is available at the link:')
    return message + '\n' + url
