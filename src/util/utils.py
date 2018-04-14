import json

from django.conf import settings
from django.http import HttpResponse


class JsonResponse(object):
    @classmethod
    def success(cls, data=None):
        return cls.__base_response(200, data)

    @classmethod
    def method_error(cls, current_method, expected_method):
        return cls.__base_error_response(
            400,
            'MethodException',
            'Invalid method <{}>, expected <{}>'.format(current_method, expected_method)
        )

    @classmethod
    def value_error(cls, msg):
        return cls.__base_error_response(400, 'ValueException', msg)

    @classmethod
    def already_exists_error(cls, msg=''):
        return cls.__base_error_response(400, 'AlreadyExist', msg)

    @classmethod
    def does_not_exists_error(cls, msg=''):
        return cls.__base_error_response(400, 'DoesNotExist', msg)

    @classmethod
    def auth_error(cls):
        return cls.__base_error_response(400, 'AuthError', 'No such user or password incorrect')

    @classmethod
    def auth_required(cls):
        return cls.__base_error_response(403, 'AuthRequired')

    @classmethod
    def csrf_required(cls):
        return cls.__base_error_response(403, 'CsrfTokenRequired')

    @classmethod
    def internal_error(cls, msg=''):
        return cls.__base_error_response(500, 'InternalError', msg)

    @classmethod
    def __base_error_response(cls, code, error_type, error_message=''):
        response_data = {
            'error_type': error_type,
            'error_message': error_message
        }
        return cls.__base_response(code, response_data)

    @classmethod
    def __base_response(cls, code, data):
        response_data = {
            'code': code,
            'data': data
        }
        return HttpResponse(json.dumps(response_data, separators=(',', ':')), content_type="application/json")


def api_method(method, form_cls=None, auth_required=True):
    def decor(func):
        def wrapper(request, *args, **kwargs):
            if auth_required and not request.user.is_authenticated:
                return JsonResponse.auth_required()

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
                    return JsonResponse.internal_error()

        return wrapper
    return decor


