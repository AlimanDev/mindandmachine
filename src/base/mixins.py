import json
import logging
import traceback

from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.utils import timezone
from django.utils.timezone import now

from src.base.models import ApiLog
from src.base.permissions import get_view_func

api_log_logger = logging.getLogger('api_log')


class GetObjectByCodeMixin:
    get_object_field = 'code'

    def initial(self, request, *args, **kwargs):
        if self.request.method == 'GET':
            by_code = self.request.query_params.get('by_code', False)
        else:
            by_code = self.request.data.get('by_code', False)
        self.request.by_code = by_code
        return super(GetObjectByCodeMixin, self).initial(request, *args, **kwargs)

    def get_object(self):
        if getattr(self.request, 'by_code', False):
            self.lookup_field = self.get_object_field
            self.kwargs[self.get_object_field] = self.kwargs['pk']
        return super().get_object()


class ApiLogMixin(object):
    def initial(self, request, *args, **kwargs):
        self.log = {
            "request_datetime": timezone.now(),
        }
        super(ApiLogMixin, self).initial(request, *args, **kwargs)

    def handle_exception(self, exc):
        response = super(ApiLogMixin, self).handle_exception(exc)
        self.log["error_traceback"] = traceback.format_exc()
        return response

    def finalize_response(self, request, response, *args, **kwargs):
        response = super(ApiLogMixin, self).finalize_response(
            request, response, *args, **kwargs
        )
        user = self._get_user(request)
        if user and user.network_id:
            view_func = get_view_func(request, self)
            view_func_settings = user.network.settings_values_prop.get(
                'api_log_settings', {}).get('log_funcs', {}).get(view_func)
            if view_func_settings:
                if self.should_log(request, response, user, view_func_settings):
                    if (connection.settings_dict.get("ATOMIC_REQUESTS") and getattr(response, "exception",
                                                                                    None) and connection.in_atomic_block):
                        # response with exception (HTTP status like: 401, 404, etc)
                        # pointwise disable atomic block for handle log (TransactionManagementError)
                        connection.set_rollback(True)
                        connection.set_rollback(False)

                    self.log.update(
                        {
                            "user": user,
                            "view_func": view_func,
                            "http_method": request.method,
                            "url_kwargs": self.kwargs,
                            "query_params": request.query_params.dict(),
                            "request_path": request.path,
                            "request_data": json.dumps(request.data, cls=DjangoJSONEncoder, ensure_ascii=False),
                            "response_ms": self._get_response_ms(),
                            "response_body": self._get_response_body(request, response, user, view_func_settings),
                            "response_status_code": response.status_code,
                        }
                    )
                    try:
                        self.handle_log()
                    except Exception:
                        # ensure that all exceptions raised by handle_log
                        # doesn't prevent API call to continue as expected
                        api_log_logger.exception("Logging API call raise exception!")
        return response

    def handle_log(self):
        ApiLog.objects.create(**self.log)

    def _get_user(self, request):
        user = request.user
        if user.is_anonymous:
            return None
        return user

    def _get_response_ms(self):
        response_timedelta = now() - self.log["request_datetime"]
        response_ms = int(response_timedelta.total_seconds() * 1000)
        return max(response_ms, 0)

    def should_log(self, request, response, user, view_func_settings):
        by_code = view_func_settings.get('by_code')
        pass_by_code = getattr(self.request, 'by_code',
                               False) == by_code if by_code is not None else True  # удовл. условиям by_code
        http_methods = view_func_settings.get('http_methods', [])
        return pass_by_code and request.method in http_methods

    def _get_response_body(self, request, response, user, view_func_settings):
        if response.status_code in view_func_settings.get('save_response_codes', []):
            if response.streaming:
                rendered_content = None
            elif hasattr(response, "rendered_content"):
                rendered_content = response.rendered_content
            else:
                rendered_content = response.getvalue()

            if isinstance(rendered_content, bytes):
                rendered_content = rendered_content.decode(errors="replace")
            return rendered_content
        return ''
