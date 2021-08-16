import os

from relatorio.templates.opendocument import Template
from django.utils.translation import gettext_lazy as _

def generate_document(template_path, data):
    basic = Template(source='', filepath=template_path)
    basic_generated = basic.generate(**data).render()
    content = basic_generated.getvalue()
    return content


def get_extension(file_name):
    return os.path.splitext(file_name)[-1].lower().split('.')[-1]


MONTH_NAMES = {
    1: _('January'),
    2: _('February'),
    3: _('March'),
    4: _('April'),
    5: _('May'),
    6: _('June'),
    7: _('July'),
    8: _('August'),
    9: _('September'),
    10: _('October'),
    11: _('November'),
    12: _('December'),
}
