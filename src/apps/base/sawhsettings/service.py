import calendar
from datetime import date, timedelta

import pandas as pd
from django.conf import settings

from src.apps.base.models import SAWHSettingsMapping, WorkerPosition

class DailySawhCalculatorService:
    """Считает норму рабочих дней для каждого дня, для каждой должности"""
    def __init__(self, dt_from: date = None, dt_to: date = None):
        self.dt_from = dt_from or date.today()
        self.dt_to = dt_to or (self.dt_from + timedelta(30))

    def get_daily_sawh(self) -> list[dict]:
        positions = WorkerPosition.objects.prefetch_related(
            'default_work_type_names',
            'sawh_settings',
            'sawh_settings__mappings',
        ).exclude(default_work_type_names=None)
        daily_sawh = []
        for dttm in pd.date_range(self.dt_from, self.dt_to).tolist():
            for position in positions:
                daily_sawh.append({
                    'dt': dttm.strftime(settings.QOS_DATE_FORMAT),
                    'work_types': tuple(position.default_work_type_names.values_list('id', flat=True)),
                    'worker_position': position.id,
                    'sawh': self.calc_sawh(dttm.date(), position)
                })
        return daily_sawh
    
    @staticmethod
    def calc_sawh(dt: date, position: WorkerPosition) -> float:
        mapping = getattr(position.sawh_settings, 'mappings', SAWHSettingsMapping.objects.none()).filter(year=dt.year).first()
        month_key = f"m{dt.month}"
        if mapping and mapping.work_hours_by_months and (sawh_month := mapping.work_hours_by_months.get(month_key)):
            pass
        elif sawh_month := getattr(position.sawh_settings, 'work_hours_by_months', {}).get(month_key):
            pass
        else:
            return 0
        return round(sawh_month / calendar.monthrange(dt.year, dt.month)[1], 2) if sawh_month else 0
