from django.db.models import Func


def get_datatuple(recipients, subject, message_content, attach_file):
    datatuple = []
    for email in set(recipients):
        if email:
            datatuple.append(
                (
                    subject,
                    message_content,
                    message_content,
                    attach_file,
                    None,
                    [email]
                )
            )
    return datatuple

class RoundWithPlaces(Func):
    function = 'ROUND'
    arity = 2
    arg_joiner = '::numeric, '
