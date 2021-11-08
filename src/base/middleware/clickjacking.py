import re

from django.conf import settings
from django.middleware.clickjacking import XFrameOptionsMiddleware as XFrameOptionsMiddlewareOriginal

DEFAULT_HTTP_REFERER_PATTERN = r'^https?:\/\/([^\/]+\.)?(.+\.mindandmachine\.ru\:11111|webvisor\.com|metri[ck]a\.yandex\.(com|ru|com\.tr))\/'


class XFrameOptionsMiddleware(XFrameOptionsMiddlewareOriginal):
    def get_xframe_options_value(self, request, response):
        http_referer = request.META.get('HTTP_REFERER')
        if http_referer:
            http_referer_pattern = getattr(
                settings, 'X_FRAME_OPTIONS_ALLOWALL_PATTERN', DEFAULT_HTTP_REFERER_PATTERN)
            if re.search(http_referer_pattern, http_referer):
                return 'ALLOWALL'

        return super(XFrameOptionsMiddleware, self).get_xframe_options_value(request, response)
