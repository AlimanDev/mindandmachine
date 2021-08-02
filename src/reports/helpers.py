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
