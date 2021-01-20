import os

from relatorio.templates.opendocument import Template


def generate_document(template_path, data):
    basic = Template(source='', filepath=template_path)
    basic_generated = basic.generate(**data).render()
    content = basic_generated.getvalue()
    return content


def get_extension(file_name):
    return os.path.splitext(file_name)[-1].lower().split('.')[-1]


MONTH_NAMES = {
    1: 'Январь',
    2: 'Февраль',
    3: 'Март',
    4: 'Апрель',
    5: 'Май',
    6: 'Июнь',
    7: 'Июль',
    8: 'Август',
    9: 'Сентябрь',
    10: 'Октябрь',
    11: 'Ноябрь',
    12: 'Декабрь',
}
