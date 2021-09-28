import io
import json

import pandas as pd

from src.exchange.models import SystemExportStrategy
from src.reports.utils.pivot_tabel import PlanAndFactPivotTabel
from src.timetable.models import PlanAndFactHours, WorkerDay
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


class ExportPlanAndFactHoursStrategy(BaseSystemExportStrategy):
    def execute(self):
        res = {}
        dates_dict = self.period.get_dates()
        dt_from = dates_dict.get('dt_from')
        dt_to = dates_dict.get('dt_to')
        file_obj = io.BytesIO()
        df = pd.DataFrame(list(PlanAndFactHours.objects.filter(
            dt__gte=dt_from,
            dt__lte=dt_to,
            wd_type__in=WorkerDay.TYPES_WITH_TM_RANGE,  # переделать на wd_type__is_dayoff=False
        ).values_list(
            'dt',
            'worker_fio',
            'tabel_code',
            'shop_name',
            'wd_type',
            'work_type_name',
            'plan_work_hours',
            'fact_work_hours',
        )), columns=[
            'Дата',
            'ФИО',
            'Табельный номер',
            'Подразделение',
            'Тип дня',
            'Тип работ',
            'Плановые часы',
            'Фактические часы',
        ])
        df.to_excel(file_obj, index=False)
        file_obj.seek(0)
        filename = f'plan_and_fact_hours_{dt_from}-{dt_to}.xlsx'
        self.fs_engine.write_file(filename, file_obj)
        return res


SYSTEM_EXPORT_STRATEGIES_DICT = {
    SystemExportStrategy.WORK_HOURS_PIVOT_TABLE: ExportPivotTableStrategy,
    SystemExportStrategy.PLAN_AND_FACT_HOURS_TABLE: ExportPlanAndFactHoursStrategy,
}
