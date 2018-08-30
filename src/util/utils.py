import json

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import HttpResponse
from src.db.models import (
    User,
    Shop
)


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
    def multiple_objects_returned(cls, msg=''):
        return cls.__base_error_response(400, 'MultipleObjectsReturned', msg)

    @classmethod
    def auth_error(cls):
        return cls.__base_error_response(400, 'AuthError', 'No such user or password incorrect')

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
        return HttpResponse(json.dumps(response_data, separators=(',', ':')), content_type='application/json')


def api_method(
        method,
        form_cls=None,
        auth_required=True,
        check_permissions=True,
        groups=None,
        lambda_func=None
    ):
    """

    :param method:
    :param form_cls:
    :param auth_required:
    :param check_permissions: bool, отображает нужно ли делать проверку на доступ к функциям
    :param groups: User.group_type list: группы доступа к функциям
    :param lambda_func: False -- on object creation, функция которая исходя из данных формирует данные необходимые для проверки доступа
    :return:
    """
    def decor(func):
        def wrapper(request, *args, **kwargs):
            if auth_required and not request.user.is_authenticated and settings.QOS_DEV_AUTOLOGIN_ENABLED:
                user = authenticate(request, username=settings.QOS_DEV_AUTOLOGIN_USERNAME, password=settings.QOS_DEV_AUTOLOGIN_PASSWORD)
                if user is None:
                    return JsonResponse.internal_error('cannot dev_autologin')
                login(request, user)

            if auth_required and not request.user.is_authenticated:
                return JsonResponse.auth_required()

            if request.method != method:
                return JsonResponse.method_error(request.method, method)

            form = None

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

            if check_permissions:  # for signout
                if auth_required and request.user.is_authenticated:
                    user_group = request.user.group

                    if lambda_func is None:
                        cleaned_data = Shop.objects.filter(id=form.cleaned_data['shop_id']).first()
                    else:
                        try:
                            cleaned_data = lambda_func(form.cleaned_data)
                        except:
                            return JsonResponse.does_not_exists_error()

                    if groups is None:
                        if method == 'GET':
                            __groups = User.__except_cashiers__
                        elif method == 'POST':
                            __groups = User.__allowed_to_modify__
                        else:
                            return JsonResponse.method_error(method, '')
                    else:
                        __groups = groups

                    shop_id = None
                    super_shop_id = None

                    if cleaned_data is not None:
                        if user_group in __groups:
                            if cleaned_data is False:
                                pass
                            elif user_group == User.GROUP_CASHIER:
                                if request.user.id != cleaned_data.id:
                                    return JsonResponse.access_forbidden(
                                        'You are not allowed to get other cashiers information'
                                    )
                            elif user_group == User.GROUP_MANAGER:
                                if isinstance(cleaned_data, User):
                                    shop_id = cleaned_data.shop_id
                                elif isinstance(cleaned_data, Shop):
                                    shop_id = cleaned_data.id
                                if request.user.shop_id != shop_id:
                                    return JsonResponse.access_forbidden(
                                        'You are not allowed to modify outside of your shop'
                                    )
                            elif user_group == User.GROUP_DIRECTOR or user_group == User.GROUP_SUPERVISOR:
                                if isinstance(cleaned_data, User):
                                    super_shop_id = cleaned_data.shop.super_shop_id
                                elif isinstance(cleaned_data, Shop):
                                    super_shop_id = cleaned_data.super_shop_id
                                if request.user.shop.super_shop_id != super_shop_id:
                                    return JsonResponse.access_forbidden(
                                        'You are not allowed to modify outside of your super_shop'
                                    )
                            elif user_group == User.GROUP_HQ:
                                if request.method != 'GET':
                                    JsonResponse.access_forbidden(
                                        'You are not allowed to modify any information'
                                    )

                        else:
                            return JsonResponse.access_forbidden('Your group is {}'.format(user_group))

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
