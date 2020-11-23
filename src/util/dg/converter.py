import logging
from urllib.parse import urljoin

import requests
from django.conf import settings
from django.core.files import File

from src.util.dg.helpers import get_extension
from src.util.http import make_retry_session

logger = logging.getLogger('converter')


class ConversionError(Exception):
    def __init__(self, text=''):
        self.text = text


class ConversionEngine:
    max_retries = 1
    timeout = 15

    def __init__(self, input_file, input_ext, output_ext):
        self.input_file = input_file
        if isinstance(input_file, File) and input_file.name:
            input_ext = get_extension(input_file)
        input_file_name = 'file'
        if input_ext:
            input_file_name = '{}.{}'.format(input_file_name, input_ext)
        self.input_file_name = input_file_name
        self.input_ext = input_ext
        self.output_ext = output_ext

    def get_converter_url(self):
        raise NotImplementedError()

    def get_request_params(self):
        return {}

    def _send_request(self):
        request_url = self.get_converter_url()
        session = make_retry_session(total_retires=1, backoff_factor=0.3)
        r = session.post(
            request_url,
            params=self.get_request_params(),
            files={
                'file': (self.input_file_name, self.input_file),
            },
            timeout=self.timeout,
        )
        r.raise_for_status()

        return r.content

    def convert(self):
        retries = 0
        last_exception = None
        while retries <= self.max_retries:
            try:
                output_file_content = self._send_request()

            except requests.Timeout as e:
                logger.exception(e)
                retries += 1
                last_exception = e

            except requests.RequestException as e:
                logger.exception(e)
                raise ConversionError from e

            else:
                return output_file_content

        raise ConversionError('Max retries exceeded') from last_exception


class LibreOfficeConversionEngine(ConversionEngine):
    def get_converter_url(self):
        return urljoin(settings.JOD_CONVERTER_URL, '/conversion')

    def get_request_params(self):
        return {
            'format': self.output_ext,
        }


class GotenbergPDFConversionEngine(ConversionEngine):
    input_ext_to_resource_mapping = {
        'ods': '/convert/office',
        'odt': '/convert/office',
    }

    def get_converter_url(self):
        return urljoin(settings.GOTENBERG_URL, self.input_ext_to_resource_mapping.get(self.input_ext))


class DocConverter:
    output_ext_to_conversion_engine_mapper = {
        'pdf': GotenbergPDFConversionEngine,
        'docx': LibreOfficeConversionEngine,
        'xlsx': LibreOfficeConversionEngine,
        'html': LibreOfficeConversionEngine,
    }

    @classmethod
    def convert(cls, input_file, input_ext=None, output_ext='pdf'):
        conversion_engine_cls = cls.output_ext_to_conversion_engine_mapper.get(output_ext)
        convertion_engine = conversion_engine_cls(
            input_file=input_file,
            input_ext=input_ext,
            output_ext=output_ext,
        )
        return convertion_engine.convert()
