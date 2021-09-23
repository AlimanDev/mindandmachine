import re
import mimetypes

from django.utils.html import strip_tags
from django.core.mail import get_connection, EmailMultiAlternatives


def textify(html):
    # Remove html tags and continuous whitespaces
    text_only = re.sub('[ \t]+', ' ', strip_tags(html))
    # Strip single spaces in the beginning of each line
    return text_only.replace('\n ', '\n').strip()



def send_mass_html_mail(datatuple, fail_silently=False, user=None, password=None,
                        connection=None):
    """
    Given a datatuple of (
        subject, 
        text_content, 
        html_content, 
        {
            'name': str or None,
            'file': IOBytes,
            'type': str or None,
        }, 
        from_email,
        recipient_list,
    ), 
    sends each message to each recipient list. Returns the
    number of emails sent.

    If from_email is None, the DEFAULT_FROM_EMAIL setting is used.
    If auth_user and auth_password are set, they're used to log in.
    If auth_user is None, the EMAIL_HOST_USER setting is used.
    If auth_password is None, the EMAIL_HOST_PASSWORD setting is used.

    """
    connection = connection or get_connection(
        username=user, password=password, fail_silently=fail_silently)
    messages = []
    for subject, text, html, file_data, from_email, recipient in datatuple:
        message = EmailMultiAlternatives(subject, text, from_email, recipient)
        message.attach_alternative(html, 'text/html')
        if file_data and file_data.get('file'):
            message.attach(file_data.get('name', 'No name'), file_data['file'].getvalue(), file_data.get('type', mimetypes.guess_type(file_data.get('name', 'No name'))[0]))
        messages.append(message)
    return connection.send_messages(messages)
