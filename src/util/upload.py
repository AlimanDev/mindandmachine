from src.conf.djconfig import ALLOWED_UPLOAD_EXTENSIONS
from django.utils.datastructures import MultiValueDictKeyError
from functools import wraps
from src.base.exceptions import MessageError


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
            raise MessageError(code='upload_no_files', lang=request.user.lang)

        if not file:
            raise MessageError(code='upload_no_file', lang=request.user.lang)
        if not file.name.split('/')[-1].split('.', file.name.split('/')[-1].count('.'))[-1] in ALLOWED_UPLOAD_EXTENSIONS:
            raise MessageError(code='upload_incorrect_extension', lang=request.user.lang)

        return func(view, request, file, *args, **kwargs)
    return wrapper
