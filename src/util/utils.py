import json
import sys
from functools import wraps

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.core import mail
from django.core.exceptions import (
    ObjectDoesNotExist,
    MultipleObjectsReturned,
)
from django.http import HttpResponse
from django.views.debug import ExceptionReporter
from django.views.decorators.csrf import csrf_exempt
from django.utils.timezone import now

from src.base.models import (
    Employment,
    FunctionGroup,
    Shop,
    User,
)


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
        return cls.__base_error_response(404, 'DoesNotExist', msg)

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
            content_type='application/json',
            status=code,
        )


def api_method(
        method,
        form_cls=None,
        auth_required=True,
        check_permissions=True,
        lambda_func=None,
        check_password=False,
        allow_empty_shop=False,
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
        lambda_func(function): функция которая исходя из данных формирует данные
           необходимые для проверки доступа. при создании объекта -- False
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
                # чтобы ошибок не было тогда, когда токен не подходит -- или стоит показывать что не прошла авторизация?
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

            if check_permissions and auth_required:
                skip_check_permissions=False
                if lambda_func:
                    try:
                        shop = lambda_func(form.cleaned_data)
                    except ObjectDoesNotExist:
                        return JsonResponse.does_not_exists_error("Can't get shop")
                    except MultipleObjectsReturned:
                        return JsonResponse.multiple_objects_returned()
                    if shop is None:
                        if allow_empty_shop:
                            skip_check_permissions = True
                        else:
                            return JsonResponse.does_not_exists_error('No such department')

                else:
                    if form.cleaned_data.get('shop_id'):
                        shop = Shop.objects.filter(id=form.cleaned_data['shop_id']).first()
                        if not shop:
                            return JsonResponse.does_not_exists_error('No such department')
                    else:
                        return JsonResponse.value_error('No shop id')
                        # shop = request.user.shop


                request.shop = shop
                if not skip_check_permissions:
                    dt = now().date()

                    employments = Employment.objects.get_active(
                        dt, dt,
                        shop__in=shop.get_ancestors(include_self=True, ascending=True),
                        user=request.user)

                    if not len(employments):
                        return JsonResponse.access_forbidden(
                            'Вы не можете просматрировать информацию по другим магазинам'
                        )

                    function_group_id = list(employments.values_list('function_group_id', flat=True))
                    if not len(function_group_id):
                        return JsonResponse.internal_error(
                            'У пользователя {} {} не указана группа'.format(
                                request.user.first_name,
                                request.user.last_name
                            )
                        )

                    function_to_check = FunctionGroup.objects.filter(group__id__in=function_group_id,
                                                                     func=func.__name__).first()
                    if function_to_check is None:
                        return JsonResponse.access_forbidden(
                            'Для вашей группы пользователей не разрешено просматривать или изменять запрашиваемые данные.'
                        )
                    authorized=False
                    for employment in employments:
                        parent = employment.shop
                        level = parent.get_level_of(shop)
                        if level <= function_to_check.level_down:
                            authorized=True
                            break

                    if not authorized:
                        return JsonResponse.access_forbidden(
                            'Вы не можете просматрировать информацию по другим магазинам'
                        )
            try:
                return func(request, *args, **kwargs)
            except Exception as e:
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

