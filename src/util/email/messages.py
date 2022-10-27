from django.utils.translation import gettext as _


def prepare_message_tick_report(url: str):
    message = _("""\
Your employee monitoring report is ready to be downloaded.
You can access it by the following link:

{}

Warning: the link will expire at the end of the business day. Please use employee monitoring generation form in the application to create a new version."""
    ).format(url)
    return message
