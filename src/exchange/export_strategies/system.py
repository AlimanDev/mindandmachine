from .base import BaseExportStrategy


class BaseSystemExportStrategy(BaseExportStrategy):
    pass


class ExportPivotTable(BaseSystemExportStrategy):
    pass


SYSTEM_EXPORT_STRATEGIES_DICT = {
    'work_hours_pivot_table': ExportPivotTable,
}
