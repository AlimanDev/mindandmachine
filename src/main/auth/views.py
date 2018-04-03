from django.contrib.auth import authenticate, login, logout
from django.middleware.csrf import rotate_token

from src.db.models import User
from src.util.models_converter import UserConverter
from src.util.utils import JsonResponse, api_method
from .forms import SigninForm


@api_method('GET', auth_required=False)
def update_csrf(request):
    rotate_token(request)
    return JsonResponse.success()


@api_method('POST', SigninForm, auth_required=False)
def signin(request, form):
    if not request.user.is_authenticated:
        user = authenticate(request, username=form['username'], password=form['password'])
        if user is None:
            return JsonResponse.auth_error()

        login(request, user)

    user = User.objects.get(id=request.user.id)
    data = UserConverter.convert(user)

    return JsonResponse.success(data)


@api_method('POST')
def signout(request):
    logout(request)
    rotate_token(request)

    return JsonResponse.success()


@api_method('GET', auth_required=False)
def is_signed(request):
    data = {
        'is_signed': request.user.request.user.is_authenticated
    }

    if request.user.is_authenticated:
        user = User.objects.get(id=request.user.id)
        data['user'] = UserConverter.convert(user)

    return JsonResponse.success(data)
