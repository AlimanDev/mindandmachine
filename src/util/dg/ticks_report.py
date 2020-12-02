import os
from datetime import datetime

from django.conf import settings

from .base import BaseDocGenerator


class TicksReportGenerator(BaseDocGenerator):
    def __init__(self, ticks_queryset):
        self.ticks_queryset = ticks_queryset

    def get_data(self):
        data = {
            'ticks': list(
                self.ticks_queryset.select_related(
                    'user', 'tick_point', 'tick_point__shop'
                )
            ),
            'dt_now': datetime.now()
        }
        return data


class TicksOdsReportGenerator(TicksReportGenerator):
    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/ticks_report.ods')


class TicksOdtReportGenerator(TicksReportGenerator):
    def get_template_path(self):
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/ticks_report.odt')