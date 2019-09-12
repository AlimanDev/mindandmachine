from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware as DjangoCsrfViewMiddleware

from src.util.utils import JsonResponse


class CsrfMiddleware(DjangoCsrfViewMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if settings.QOS_DEV_CSRF_DISABLED:
            return # dev

        request.is_mobile = False
        if "Expo" in request.META.get('HTTP_USER_AGENT', '') or "okhttp/3.6.0" in request.META.get(
                'HTTP_USER_AGENT', ''):
            request.is_mobile = True
            return # mobile app

        # todo: нужно красиво все разделять. Из последовательность middleware сначала авторизация, потом проврека csrf токена
        # нельзя, чтобы отправлялась форма без  csrf токеном от пользователя. Поэтому идет проверка авторизованный ли пользователь
        # велосипед, авторизация должна раньше идти и поле храниться, но тогда не показать, что функция только для авторизованных
        if (not request.user.is_authenticated) and (request.POST.get('access_token', None) or request.GET.get('access_token', None)):
            return # access by token

        response = super().process_view(request, callback, callback_args, callback_kwargs)
        if response is not None:
            return JsonResponse.csrf_required()