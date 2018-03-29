import json

from django.http import HttpResponse
from django.conf import settings


class JsonResponse(object):
    @classmethod
    def success(cls, data=None):
        return cls.base_response(200, data)

    @classmethod
    def method_error(cls, current_method, expected_method):
        return JsonResponse.base_error_response(400, 'MethodException', 'Invalid method <{}>, expected <{}>'.format(current_method, expected_method))

    @classmethod
    def value_error(cls, msg):
        return JsonResponse.base_error_response(400, 'ValueException', msg)

    @classmethod
    def base_error_response(cls, code, error_type, error_message):
        response_data = {
            'error_type': error_type,
            'error_message': error_message
        }
        return cls.base_response(code, response_data)

    @classmethod
    def base_response(cls, code, data):
        response_data = {
            'code': code,
            'data': data
        }
        return HttpResponse(json.dumps(response_data, separators=(',', ':')), content_type="application/json")


def api_method(method, form_cls=None, auth_required=True):
    def decor(func):
        def wrapper(request, *args, **kwargs):
            if auth_required and not request.user.is_authenticated:
                return JsonResponse.base_error_response(403, 'AuthRequired', '')

            if request.method != method:
                return JsonResponse.method_error(request.method, method)

            if form_cls is not None:
                if request.method == 'GET':
                    form_params = request.GET
                elif request.method == 'POST':
                    form_params = request.POST
                else:
                    form_params = {}

                form = form_cls(form_params)
                if not form.is_valid():
                    return JsonResponse.value_error(str(list(form.errors.items())))

                kwargs['form'] = form.cleaned_data
            else:
                kwargs.pop('form', None)

            try:
                return func(request, *args, **kwargs)
            except Exception as e:
                if settings.DEBUG:
                    raise e
                else:
                    # todo: add logging at DEBUG = False
                    return JsonResponse.base_error_response(500, 'InternalError', 'Internal server error occurred')

        return wrapper
    return decor


def count(collection, comparer):
    c = 0
    for x in collection:
        if comparer(x):
            c += 1
    return c

