from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import rotate_token

from src.db.models import User
from src.util.models_converter import UserConverter
from src.util.utils import JsonResponse, api_method
from .forms import SigninForm


@api_method('GET', auth_required=False, check_permissions=False)
def update_csrf(request):
    """
    Обновляет csrf токен

    Args:
        method: GET
        url: api/auth/update_csrf
    """
    rotate_token(request)
    return JsonResponse.success()


@api_method('POST', SigninForm, auth_required=False, check_permissions=False)
def signin(request, form):
    """
    Авторизация

    Args:
        method: POST
        url: api/auth/signin
        username(str):
        password(stt):

    Returns:
        (User): user instance
    """
    if not request.user.is_authenticated:
        user = authenticate(request, username=form['username'], password=form['password'])
        if user is None:
            return JsonResponse.auth_error()

        login(request, user)
    user = User.objects.get(id=request.user.id)

    return JsonResponse.success(UserConverter.convert(user))


@api_method('POST', check_permissions=False)
def signout(request):
    """
    Выход из учетной записи

    Args:
         method: POST
         url: api/auth/signout
    """
    logout(request)
    rotate_token(request)

    return JsonResponse.success()


@api_method('GET', auth_required=False, check_permissions=False)
def is_signed(request):
    """
    Проверяет что пользователь авторизован

    Args:
        method: GET
        url: api/auth/is_signed
    Returns:
        (User): user instance
    """
    data = {
        'is_signed': request.user.is_authenticated
    }

    if request.user.is_authenticated:
        user = User.objects.get(id=request.user.id)
        data['user'] = UserConverter.convert(user)

    return JsonResponse.success(data)
