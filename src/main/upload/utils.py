from src.util.utils import JsonResponse
from src.conf.djconfig import ALLOWED_UPLOAD_EXTENSIONS
from django.utils.datastructures import MultiValueDictKeyError
from django.conf import settings
from src.db.models import WorkerDay
from functools import wraps


WORK_TYPES = {
    'В': WorkerDay.Type.TYPE_HOLIDAY.value,
    'ОТ': WorkerDay.Type.TYPE_VACATION.value,
}


def get_uploaded_file(func):
    """
    Проверят загруженный на сервак файл(есть ли вообще файл в запросе и какого он формата)
    18.11.2018 -- пока поддерживаем только excel

    Args:
        request(WSGIrequest): request

    Returns:
        file
    """
    @wraps(func)
    def wrapper(request, form, *args, **kwargs):
        try:
            file = request.FILES['file']
        except MultiValueDictKeyError:
            return JsonResponse.value_error('Не было передано ни одного файла.')

        if not file:
            return JsonResponse.value_error('Файл не был загружен.')
        if not file.name.split('.', file.name.count('.'))[-1] in ALLOWED_UPLOAD_EXTENSIONS:
            return JsonResponse.value_error('Файлы с таким расширением не поддерживается.')

        try:
            return func(request, form, file, *args, **kwargs)
        except Exception as e:
            print(e)
            if settings.DEBUG:
                raise e
            else:
                return JsonResponse.internal_error('error in get_uploaded_file decorator')
    return wrapper
