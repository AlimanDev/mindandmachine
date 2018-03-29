from django.contrib.auth import authenticate, login, logout
# from django.views.decorators.csrf import ensure_csrf_cookie

from src.util.utils import JsonResponse, api_method
from .forms import SigninForm


# @ensure_csrf_cookie
# @api_method('GET', auth_required=False)
# def update_csrf(request):
#     return JsonResponse.success()


@api_method('POST', SigninForm, auth_required=False)
def signin(request, form):
    user = authenticate(request, username=form['username'], password=form['password'])
    if user is None:
        return JsonResponse.base_error_response(400, 'AuthError', 'No such user or password incorrect')

    login(request, user)
    return JsonResponse.success()


@api_method('POST')
def signout(request):
    logout(request)
    return JsonResponse.success()
