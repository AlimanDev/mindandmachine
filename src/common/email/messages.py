from django.utils.translation import gettext as _


def prepare_message_for_report(report_name: str, url: str) -> str:
    message = _("""\
Your {report_name} is ready to be downloaded.
You can access it by the following link:

{url}

Warning: the link will expire at the end of the business day. Please use the generation form in the application to create a new version."""
    ).format(report_name=report_name, url=url)
    return message

def report_error_message() -> str:
    return _('There has been an error generating your report.\nPlease contact the technical support.')
