import io

import pandas as pd
import numpy as np
import xlsxwriter
from django.http.response import HttpResponse
from django.utils.encoding import escape_uri_path
from django.utils.translation import gettext as _

from src.timetable.models import PlanAndFactHours


class Columns:
    NETWORK = 0
    SHOP = 1
    WORK_TYPE = 2
    TABEL_CODE = 3
    FIO = 4
    FIRST_DATE = 5

class BasePivotTabel:
    fields_mapping = None
    values_field = None
    index_fields = [_('Employee network'), _('Department'), _('Work type'), _('Tabel code'), _('Full name')]
    columns_fields = None

    def __init__(self):
        if not (self.fields_mapping and self.values_field and self.index_fields and self.columns_fields):
            raise NotImplementedError()

    def get_data(self, **kwargs):
        raise NotImplementedError()

    def get_pivot_file(self, **kwargs):
        df = pd.DataFrame(self.get_data(**kwargs)).fillna('')
        df = df.rename(columns=self.fields_mapping)
        if not len(df.values):
            return None
        table = pd.pivot_table(df, values=self.values_field, index=self.index_fields, columns=self.columns_fields, aggfunc=np.sum, fill_value=0)
        table[_('Hours in period')] = table.sum(axis=1).values
        table = np.round(
            table.append(                                           # TODO: rewrite to pd.concat somehow (pivot_table does not seem to concat here correctly)
                table.sum().rename(('', '', '', '', _('TOTAL'))) 
            ), 
            2
        )
        table = table.reset_index()
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        table.to_excel(
            excel_writer=writer, sheet_name=_('Tabel'), index=False
        )
        worksheet = writer.sheets[_('Tabel')]

        base_format = {
            'valign': 'vcenter',
            'align': 'center',
            'text_wrap': True,
        }
        cell_format1 = writer.book.add_format(base_format)
        for r in range(len(table.values)):
            worksheet.set_row(r, None, cell_format1)
        base_format['border'] = True
        cell_format2 = writer.book.add_format(base_format)
        worksheet.conditional_format(
            xlsxwriter.utility.xl_range(1, Columns.NETWORK, len(table) - 1, Columns.FIRST_DATE),
            {'type': 'no_errors', 'format': cell_format2}
        )
        worksheet.conditional_format(
            xlsxwriter.utility.xl_range(1, Columns.FIRST_DATE, len(table) - 1, Columns.FIRST_DATE + df['dt'].nunique()),
            {'type': 'no_blanks', 'format': cell_format2}
        )
        base_format.update({'border': False, 'bold': True})
        cell_format3 = writer.book.add_format(base_format)
        worksheet.set_row(0, None, cell_format3)
        worksheet.set_row(len(table.values), None, cell_format3)

        worksheet.set_column(Columns.NETWORK, Columns.NETWORK, 20)
        worksheet.set_column(Columns.SHOP, Columns.SHOP, 20)
        worksheet.set_column(Columns.WORK_TYPE, Columns.WORK_TYPE, 15)
        worksheet.set_column(Columns.TABEL_CODE, Columns.TABEL_CODE, 38)
        worksheet.set_column(Columns.FIO, Columns.FIO, 33)
        worksheet.set_column(Columns.FIRST_DATE, len(table.columns) - 2, 10) # Dates
        worksheet.set_column(len(table.columns) - 2, len(table.columns) - 1, 18) # Hours in period
        writer.book.close()
        output.seek(0)
        return output

    def get_response(self, output_name=_('Pivot tabel'), **kwargs):
        output = self.get_pivot_file(**kwargs)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(output_name))
        return response


class PlanAndFactPivotTabel(BasePivotTabel):
    fields_mapping = {
        'worker__network__name': 'Сеть сотрудника',
        'shop_name': 'Подразделение',
        'work_type_name': 'Тип работ',
        'tabel_code': 'Табельный номер',
        'worker_fio': 'ФИО',
    }
    values_field = 'fact_work_hours'
    columns_fields = ['dt']

    def get_data(self, **kwargs):
        dt_from = kwargs.get('dt__gte')
        dt_to = kwargs.get('dt__lte')
        data = list(
            PlanAndFactHours.objects.select_related(
                'worker__network',
            ).filter(
                fact_work_hours__gt=0,
            ).filter(
                **kwargs,
            ).values(
                'worker__network__name', 
                'shop_name', 
                'worker_fio', 
                'fact_work_hours', 
                'dt', 
                'tabel_code', 
                'work_type_name'
            )
        )
        if data:
            dates = set(map(lambda x: x['dt'], data))
            need_dates = set(pd.date_range(dt_from or min(dates), dt_to or max(dates)).date) - dates
            worker_fill = data[0].copy()
            for dt in need_dates:
                wf = worker_fill.copy()
                wf['dt'] = dt
                wf['fact_work_hours'] = 0.0
                data.append(wf)
        return data
