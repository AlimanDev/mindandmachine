from django.utils.translation import gettext as _
from rest_framework.serializers import ValidationError
from src.conf.djconfig import ALLOWED_UPLOAD_EXTENSIONS
from django.utils.datastructures import MultiValueDictKeyError
from functools import wraps


def get_uploaded_file(func):
    """
    Проверят загруженный на сервак файл(есть ли вообще файл в запросе и какого он формата)
    18.11.2018 -- пока поддерживаем только excel
    запускать с api_method
    Args:
        request(WSGIrequest): request
    Returns:
        file
    """
    @wraps(func)
    def wrapper(view, request, *args, **kwargs):
        try:
            file = request.FILES['file']
        except MultiValueDictKeyError:
            raise ValidationError(_('No files were transferred.'))

        if not file:
            raise ValidationError(_('The file was not uploaded.'))
        if not file.name.split('/')[-1].split('.', file.name.split('/')[-1].count('.'))[-1] in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValidationError(_('Files with this extension are not supported.'))

        return func(view, request, file, *args, **kwargs)
    return wrapper
