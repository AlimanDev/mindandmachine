from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import rotate_token
from django.utils import timezone
from django.db.models import Q
from fcm_django.models import FCMDevice

from src.base.models import User, Employment
from src.util.models_converter import UserConverter
from src.util.utils import JsonResponse, api_method
from .forms import SigninForm, FCMTokenForm


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
        employments = Employment.objects.filter(
            Q(dt_fired__gt=timezone.now().date())| Q(dt_fired__isnull=True),
            dt_hired__lte=timezone.now().date(),
            user=user,
        )
        if not employments.exists():
            return JsonResponse.not_active_error()
        login(request, user)
    # user = User.objects.select_related('position').get(id=request.user.id)

    return JsonResponse.success(UserConverter.convert(request.user))


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


@api_method('POST', FCMTokenForm, check_permissions=False)
def rotate_fcm_token(request, form):
    user_id = request.user.id
    FCMDevice.objects.filter(user_id=user_id).delete()
    FCMDevice.objects.create(
        user_id=user_id,
        registration_id=form['fcm_token'],
        type=form['platform']
    )
    return JsonResponse.success()
