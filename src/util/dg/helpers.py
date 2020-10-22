import os

from relatorio.templates.opendocument import Template


def generate_document(template_path, data):
    basic = Template(source='', filepath=template_path)
    basic_generated = basic.generate(**data).render()
    content = basic_generated.getvalue()
    return content


def get_extension(file_name):
    return os.path.splitext(file_name)[-1].lower().split('.')[-1]
