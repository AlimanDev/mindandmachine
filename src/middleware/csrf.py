from django.middleware.csrf import CsrfViewMiddleware as DjangoCsrfViewMiddleware

from src.util.utils import JsonResponse


class CsrfMiddleware(DjangoCsrfViewMiddleware):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def process_view(self, request, callback, callback_args, callback_kwargs):
        response = super().process_view(request, None, (), {})
        if response is not None:
            return JsonResponse.csrf_required()
