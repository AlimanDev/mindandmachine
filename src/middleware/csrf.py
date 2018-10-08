from django.conf import settings
from django.middleware.csrf import CsrfViewMiddleware as DjangoCsrfViewMiddleware

from src.util.utils import JsonResponse


class CsrfMiddleware(DjangoCsrfViewMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_view(self, request, callback, callback_args, callback_kwargs):
        if settings.QOS_DEV_CSRF_DISABLED:
            return

        if "Expo" in request.META['HTTP_USER_AGENT'] or "okhttp/3.6.0" in request.META['HTTP_USER_AGENT']:
            return

        response = super().process_view(request, callback, callback_args, callback_kwargs)
        if response is not None:
            return JsonResponse.csrf_required()
