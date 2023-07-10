from functools import wraps

from django.conf import settings

from src.common import email, files

def mailable_report(report_name):
    """
    If emails is passed - save report on server, send link via email.
    Also email if any errors occur during generation.
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, emails: list[str] = None, **kwargs):
            if not emails: # return normal report
                return func(*args, **kwargs)
            try:
                report = func(*args, **kwargs)
                file = files.save_on_server(
                    report['file'],
                    report['name'],
                    directory=settings.REPORTS_ROOT,
                    serve_url=settings.REPORTS_URL
                )
                message = email.prepare_message_for_report(
                    report_name.lower(),
                    settings.EXTERNAL_HOST + file.url
                )
                email.send_email(
                    subject=report_name,
                    body=message,
                    to=emails
                )
            except: # notify user that the report generation failed
                email.send_email(
                    subject=report_name,
                    body=email.report_error_message(),
                    to=emails
                )
                raise
            # return str for flower monitoring
            return f'Report {report["name"]} sent to {", ".join(emails)}'

        return wrapper
    return decorator
