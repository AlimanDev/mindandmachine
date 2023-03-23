import os, abc, json
from typing import Any
from datetime import date

from django.conf import settings
from django.utils.translation import gettext as _

from src.recognition.models import Tick
from src.util.time import DateTimeHelper
from .base import BaseDocGenerator


class BaseTicksReportGenerator(abc.ABC):
    def __init__(self, ticks: list[Tick], dt_from: date = None, dt_to: date = None):
        self.ticks = ticks
        self.dt_from = dt_from
        self.dt_to = dt_to
    
    @abc.abstractmethod
    def generate_report(self) -> Any:
        ...

class BaseFileTicksReportGenerator(BaseDocGenerator, BaseTicksReportGenerator):
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

class TicksOdsReportGenerator(BaseFileTicksReportGenerator):
    def get_template_path(self) -> str:
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/ticks_report.ods')

    def generate_report(self):
        return super().generate(convert_to='xlsx')

class TicksOdtReportGenerator(BaseFileTicksReportGenerator):
    def get_template_path(self) -> str:
        return os.path.join(settings.BASE_DIR, 'src/util/dg/templates/ticks_report.odt')

    def generate_report(self):
        return super().generate(convert_to='docx')


class TicksJsonReportGenerator(BaseTicksReportGenerator):
    fields = {
        'id': int,
        'dttm': str,
        'type_display': str,
        'tick_kind': str,
        'outsource_network': str | None,
        'violation': str | None,
        'lateness': int | None,    # seconds
        'verified_score': float,
        'liveness': float | None,
        'biometrics_check': bool,
        'shop': {
            'id': int,
            'name': str,
            'code': str | None
        },
        'employee': {
            'id': int,
            'code': str | None,
            'tabel_code': str | None,
            'user': {
                'id': int,
                'fio': str,
            }
        }
    }

    def generate_report(self) -> str:
        tick_values = tuple(map(self._model_to_dict, self.ticks))
        return json.dumps(tick_values)

    def _model_to_dict(self, tick: Tick) -> dict:
        special_fields = ('dttm', 'lateness', 'liveness' 'employee', 'shop')    # require some parsing
        tick_dict = {
            field: getattr(tick, field, None)
            for field in self.fields if field not in special_fields
        }

        tick_dict['dttm'] = DateTimeHelper.to_dttm_str(tick.dttm)
        lateness = getattr(tick, 'lateness', None)
        tick_dict['lateness'] = getattr(lateness, 'total_seconds', lambda: None)()
        tick_dict['liveness'] = tick.min_liveness_prop
        tick_dict['shop'] = {
            'id': tick.tick_point.shop.id,
            'name': tick.tick_point.shop.name,
            'code': tick.tick_point.shop.code
        }
        tick_dict['employee'] = {
            'id': tick.employee.id,
            'code': tick.employee.code,
            'tabel_code': tick.employee.tabel_code,
            'user': {
                'id': tick.employee.user.id,
                'fio': tick.employee.user.fio,
            }
        }
        return tick_dict
