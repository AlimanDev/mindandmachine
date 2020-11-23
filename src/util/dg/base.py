from src.util.dg.converter import DocConverter
from src.util.dg.helpers import generate_document, get_extension


class BaseDocGenerator:
    """
    Базовый класс для генерации и конвертации документов
    """

    def get_template_path(self):
        raise NotImplementedError

    def get_data(self):
        raise NotImplementedError

    def generate(self, convert_to=None):
        template_path = self.get_template_path()
        content = generate_document(
            template_path=template_path,
            data=self.get_data(),
        )

        if convert_to:
            content = DocConverter.convert(
                input_file=content,
                input_ext=get_extension(template_path),
                output_ext=convert_to,
            )

        return content
