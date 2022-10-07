import os
from datetime import date

from django.conf import settings
from django.db.models.query import QuerySet
from django.utils.translation import gettext as _

from .base import BaseDocGenerator


class TicksReportGenerator(BaseDocGenerator):
    def __init__(self, ticks_queryset: QuerySet, dt_from: date = None, dt_to: date = None):
        self.ticks_queryset = ticks_queryset
        self.dt_from = dt_from
        self.dt_to = dt_to

    def get_data(self) -> dict:
        data = {
            'ticks': list(
                self.ticks_queryset.select_related(
                    'user', 'tick_point', 'tick_point__shop'
                )
            ),
            'dt_from': self.dt_from,
            'dt_to': self.dt_to,
            'title': _('Tick report'),
            'columns': {
                'fio': _('Employee'), #full name
                'tabel_code': _('Tabel code'),
                'tick_point_name': _('Tick point'),
                'shop_name': _('Shop'),
                'shop_code': _('Shop code'),
                'tick_type': _('Tick type'),
                'tick_dttm': _('Tick date and time'),
                'verified_score': _('Verified score'),
                'liveness': _('Liveness'), #quality
                'photo': _('Photo')
            }
        }
        return data


class TicksOdsReportGenerator(TicksReportGenerator):
    def get_template_path(self) -> str:
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/ticks_report.ods')


class TicksOdtReportGenerator(TicksReportGenerator):
    def get_template_path(self) -> str:
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/ticks_report.odt')
