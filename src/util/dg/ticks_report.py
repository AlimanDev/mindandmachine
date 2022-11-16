import os
from datetime import date

from django.conf import settings
from django.utils.translation import gettext as _

from .base import BaseDocGenerator


class TicksReportGenerator(BaseDocGenerator):
    def __init__(self, ticks: list, dt_from: date = None, dt_to: date = None):
        self.ticks = ticks
        self.dt_from = dt_from
        self.dt_to = dt_to

    def get_data(self) -> dict:
        # Empty photo, to not break image rendering
        with open(os.path.join(settings.BASE_DIR, 'src/util/dg/templates/no_photo.png'), 'rb') as f:
            no_photo = f.read()

        data = {
            'ticks': self.ticks,
            'dt_from': self.dt_from,
            'dt_to': self.dt_to,
            'title': _('Tick report'),
            'no_photo': (no_photo, 'image/png'),
            'columns': {
                'fio': _('Employee'), # Full employee name
                'outsource_network': _('Outsource network'),    # Network name. If not outsource - blank.
                'tabel_code': _('Tabel code'),
                'shop_name': _('Shop'),
                'tick_type': _('Tick type'),    # Arrival/Departure
                'tick_kind': _('Tick kind'),    # Autotick/Manual tick
                'violation': _('Violation'),    # Late arrival/Early departure/Late departure/Arrival without plan
                'tick_dttm': _('Tick date and time'),
                'liveness': _('Photo quality'),   # Liveness is intentionally renamed to Quality
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
