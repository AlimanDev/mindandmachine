import json

import sys
from django.core import mail
from django.views.debug import ExceptionReporter
from django.conf import settings
from functools import wraps
from django.contrib.auth import authenticate, login
from django.http import HttpResponse
from django.core.exceptions import (
    ObjectDoesNotExist,
    MultipleObjectsReturned,
)
from src.db.models import (
    User,
    Shop,
    FunctionGroup,
)
from django.views.decorators.csrf import csrf_exempt
from django.db.models import QuerySet
from datetime import datetime, timedelta


def manually_mail_admins(request):
    exc_info = sys.exc_info()
    reporter = ExceptionReporter(request, *exc_info, is_email=True)

    def exception_name():
        if exc_info[0]:
            return exc_info[0].__name__
        return 'Exception'

    def subject():
        if request:
            return '{} at {}'.format(
                exception_name(),
                request.path_info
            )
        return exception_name()

    mail.mail_admins(
        subject=subject(),
        message=reporter.get_traceback_text(),
        fail_silently=True,
        html_message=reporter.get_traceback_html()
    )


class JsonResponse(object):
    """
    Methods:
        success(data): 200
        method_error(current_method, expected_method): 400
        value_error(msg): 400
        already_exists_error(msg): 400
        does_not_exists_error(msg): 400
        multiple_objects_returned(msg): 400
        auth_error(): 400
        auth_required(): 401
        csrf_required(): 401
        access_forbidden(msg): 403
        internal_error(msg): 500
        algo_internal_error(msg): 500

    """

    @classmethod
    def success(cls, data=None, additional_info=None):
        return cls.__base_response(200, data, additional_info)

    @classmethod
    def method_error(cls, current_method, expected_method):
        return cls.__base_error_response(
            400,
            'MethodException',
            'Invalid method {}, expected {}'.format(current_method, expected_method)
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
    def multiple_objects_returned(cls, msg=''):
        return cls.__base_error_response(400, 'MultipleObjectsReturned', msg)

    @classmethod
    def auth_error(cls):
        return cls.__base_error_response(400, 'AuthError', 'No such user or password incorrect')

    @classmethod
    def not_active_error(cls):
        return cls.__base_error_response(400, 'NotActiveError', 'User is not active')

    @classmethod
    def auth_required(cls):
        return cls.__base_error_response(401, 'AuthRequired')

    @classmethod
    def csrf_required(cls):
        return cls.__base_error_response(401, 'CsrfTokenRequired')

    @classmethod
    def access_forbidden(cls, msg=''):
        return cls.__base_error_response(403, 'AccessForbidden', msg)

    @classmethod
    def internal_error(cls, msg=''):
        return cls.__base_error_response(500, 'InternalError', msg)

    @classmethod
    def algo_internal_error(cls, msg=''):
        return cls.__base_error_response(500, 'AlgorithmInternalError', msg)

    @classmethod
    def __base_error_response(cls, code, error_type, error_message=''):
        response_data = {
            'error_type': error_type,
            'error_message': error_message
        }
        return cls.__base_response(code, response_data)

    @classmethod
    def __base_response(cls, code, data, additional_info=None):
        response_data = {
            'code': code,
            'data': data,
            'info': additional_info
        }
        return HttpResponse(
            json.dumps(response_data, separators=(',', ':'), ensure_ascii=False),
            content_type='application/json'
        )


def api_method(
        method,
        form_cls=None,
        auth_required=True,
        check_permissions=True,
        lambda_func=None,
        check_password=False,
):
    """
    Note:
        Новое правило: если нужно передать список айдишников пользователей, передаем его в поле worker_ids формы

    Args:
        method(str): 'GET' or 'POST'
        form_cls: класс формы
        auth_required(bool): нужна ли авторизация для выполнения этой вьюхи
        check_permissions(bool): нужно ли делать проверку на доступ
        groups(list): список групп, которым разрешен доступ
        lambda_func(function): функция которая исходя из данных формирует данные необходимые для проверки доступа. при создании объекта -- False
        check_password(bool): запрашивать пароль на действие или нет
    """

    def decor(func):
        @wraps(func)
        def wrapper(request, *args, **kwargs):
            if auth_required and not request.user.is_authenticated and settings.QOS_DEV_AUTOLOGIN_ENABLED:
                user = authenticate(request, username=settings.QOS_DEV_AUTOLOGIN_USERNAME,
                                    password=settings.QOS_DEV_AUTOLOGIN_PASSWORD)
                if user is None:
                    return JsonResponse.internal_error('cannot dev_autologin')
                login(request, user)

            token = request.POST.get('access_token', None) or request.GET.get('access_token', None)
            if token:
                user_with_access_token = User.objects.filter(access_token=token)
                if len(user_with_access_token) == 1:
                    request.user = user_with_access_token[0]

            if auth_required and not request.user.is_authenticated:
                return JsonResponse.auth_required()

            if request.method != method:
                return JsonResponse.method_error(request.method, method)

            form = None

            if form_cls is not None:
                if request.method == 'GET':
                    form_params = request.GET
                elif request.method == 'POST':
                    if "Expo" in request.META.get('HTTP_USER_AGENT', []) or "okhttp/3.6.0" in request.META.get(
                            'HTTP_USER_AGENT', []):
                        form_params = json.loads(request.body.decode())
                    else:
                        form_params = request.POST
                else:
                    form_params = {}

                form = form_cls(form_params)
                if not form.is_valid():
                    if '__all__' in form.errors.keys():
                        return JsonResponse.value_error(form.errors['__all__'][0])
                    return JsonResponse.value_error(str(list(form.errors.items())))

                kwargs['form'] = form.cleaned_data
            else:
                kwargs.pop('form', None)

            if check_password:
                if not request.user.check_password(form.cleaned_data['password']):
                    return JsonResponse.access_forbidden('Неверный пароль')

            if check_permissions:  # for signout
                if auth_required and request.user.is_authenticated:
                    if lambda_func is None:
                        cleaned_data = Shop.objects.filter(id=form.cleaned_data['shop_id']).first()
                        if not cleaned_data:
                            return JsonResponse.internal_error('No such department')
                    else:
                        try:
                            cleaned_data = lambda_func(form.cleaned_data)
                        except ObjectDoesNotExist:
                            return JsonResponse.does_not_exists_error('error in api_method')
                        except MultipleObjectsReturned:
                            return JsonResponse.multiple_objects_returned()

                    function_group_id = request.user.function_group_id
                    if not function_group_id:
                        return JsonResponse.internal_error(
                            'У пользователя {} {} не указана группа'.format(
                                request.user.first_name,
                                request.user.last_name
                            )
                        )

                    function_to_check = FunctionGroup.objects.filter(group__id=function_group_id,
                                                                     func=func.__name__).first()
                    if function_to_check is None:
                        return JsonResponse.access_forbidden(
                            'Для вашей группы пользователей не разрешено просматривать или изменять запрашиваемые данные.'
                        )
                    else:
                        access_type = function_to_check.access_type

                    if cleaned_data is False or access_type == FunctionGroup.TYPE_ALL:
                        pass
                    else:
                        # todo: aa: делать проверку с QuerySet лучше, потому что QuerySet может быть магазинов и могут совпасть id просто
                        # (но вроде сейчас нет QuerySet таких
                        if access_type == FunctionGroup.TYPE_SELF:
                            if isinstance(cleaned_data, QuerySet):
                                if request.user.id not in cleaned_data:
                                    return JsonResponse.access_forbidden(
                                        'Вы не можете просматрировать информацию о других пользователях'
                                    )
                                else:
                                    kwargs['form']['worker_ids'] = [request.user.id]
                            elif not (isinstance(cleaned_data, User) and request.user.id == cleaned_data.id):
                                return JsonResponse.access_forbidden(
                                    'Вы не можете просматрировать информацию о других пользователях'
                                )
                        else:
                            if isinstance(cleaned_data, User):
                                cleaned_data = cleaned_data.shop
                            elif isinstance(cleaned_data, QuerySet):
                                # todo: сделать нормально во всех вьюхах
                                cleaned_data = Shop.objects.filter(user__id=cleaned_data[0]).first()

                            if access_type == FunctionGroup.TYPE_SHOP \
                                    and request.user.shop_id != cleaned_data.id:
                                return JsonResponse.access_forbidden(
                                    'Вы не можете просматрировать информацию по другим отделам'
                                )

                            elif access_type == FunctionGroup.TYPE_SUPERSHOP \
                                    and request.user.shop.super_shop_id != cleaned_data.super_shop_id:
                                return JsonResponse.access_forbidden(
                                    'Вы не можете просматрировать информацию по другим магазинам'
                                )
            try:
                return func(request, *args, **kwargs)
            except Exception as e:
                print(e)
                if settings.DEBUG:
                    raise e
                else:
                    manually_mail_admins(request)
                    return JsonResponse.internal_error('Внутренняя ошибка сервера')

        return wrapper

    return decor


def test_algo_server_connection():
    """

    Returns:
        True -- если есть соединение с "алго" серваком. Если нет, вовзращаем всякие __base_error_response
    """
    from urllib import error, request

    req = request.Request('http://{}/test'.format(settings.TIMETABLE_IP))
    try:
        response = request.urlopen(req).read().decode('utf-8')
    except error.URLError:
        return JsonResponse.algo_internal_error('Сервер для обработки алгоритма недоступен.')
    if json.loads(response)['status'] == 'ok':
        return True
    else:
        return JsonResponse.algo_internal_error('Что-то не так при подключении к серверу с алгоритмом')


def outer_server(is_camera=True, decode_body=True):
    """
    Декоратор для приема данных со сторонних серваков. Обязательно должен быть ключ в body реквеста (формта json)
    т.е. body['key']. И все данные должны быть запиханы в body['data'].

    Args:
        func(function): функция, которую надо выполнить
    """

    def decor(func):
        @csrf_exempt
        def wrapper(request, *args, **kwargs):
            if is_camera:
                access_key = settings.QOS_CAMERA_KEY
            else:
                access_key = settings.QOS_SET_TIMETABLE_KEY

            if request.method != 'POST':
                return JsonResponse.method_error(request.method, 'POST')
            try:
                if decode_body:
                    json_data = json.loads(request.body.decode('utf-8'))
                    request_key = json_data['key']
                    request_data = json_data['data']
                else:
                    request_key = request.POST['key']
                    request_data = json.loads(request.POST['data'])
            except (ValueError, TypeError):
                return JsonResponse.value_error('cannot decode body')
            # if isinstance(json_data, str):
            #     return JsonResponse.value_error('did not convert json data properly. output json data has type string')

            if access_key is not None and request_key != access_key:
                return JsonResponse.access_forbidden('invalid key')

            try:
                return func(request, request_data, *args, **kwargs)
            except Exception as e:
                print(e)
                if settings.DEBUG:
                    raise e
                else:
                    return JsonResponse.internal_error()

        return wrapper

    return decor


