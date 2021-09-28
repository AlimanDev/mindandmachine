import json

from src.exchange.models import SystemExportStrategy
from src.reports.utils.pivot_tabel import PlanAndFactPivotTabel
from .base import BaseExportStrategy


class BaseSystemExportStrategy(BaseExportStrategy):
    def __init__(self, settings_json, period, **kwargs):
        self.settings_dict = json.loads(settings_json)
        self.period = period
        super(BaseSystemExportStrategy, self).__init__(**kwargs)


class ExportPivotTableStrategy(BaseSystemExportStrategy):
    def execute(self):
        res = {}
        dates_dict = self.period.get_dates()
        dt_from = dates_dict.get('dt_from')
        dt_to = dates_dict.get('dt_to')
        pivot_file = PlanAndFactPivotTabel().get_pivot_file(
            dt__gte=dt_from,
            dt__lte=dt_to,
        )
        filename = f'pivot_table_{dt_from}-{dt_to}.xlsx'
        self.fs_engine.write_file(filename, pivot_file)
        return res


SYSTEM_EXPORT_STRATEGIES_DICT = {
    SystemExportStrategy.WORK_HOURS_PIVOT_TABLE: ExportPivotTableStrategy,
}
