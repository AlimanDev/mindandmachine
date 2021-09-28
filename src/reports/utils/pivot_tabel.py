import io
from src.timetable.models import PlanAndFactHours
import pandas as pd
import numpy as np

from django.http.response import HttpResponse
from django.utils.encoding import escape_uri_path

class BasePivotTabel:
    fields_mapping = None
    values_field = None
    index_fields = ['Сеть сотрудника', 'Подразделение', 'Тип работ', 'Табельный номер', 'ФИО']
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
        table['Часов за период'] = table.sum(axis=1).values 
        table = np.round(
            table.append( 
                table.sum().rename(('\n', '\n', '\n', 'Общий', 'итог')) 
            ), 
            2
        )
        output = io.BytesIO()
        writer = pd.ExcelWriter(output, engine='xlsxwriter')
        table.to_excel(
            excel_writer=writer, sheet_name='Табель',
        )
        worksheet = writer.sheets['Табель']
        cell_format = writer.book.add_format({
            'valign': 'vcenter',
            'align': 'center',
            'text_wrap': True,
        })
        worksheet.set_column(0, 0, 15)
        worksheet.set_column(1, 1, 20)
        for r in range(len(table.values) + 1):
            worksheet.set_row(r, None, cell_format)
        worksheet.set_column(2, 2, 15)
        worksheet.set_column(3, 3, 38)
        worksheet.set_column(4, 4, 33)
        worksheet.set_column(5, len(table.columns) + 3, 10, None)
        worksheet.set_column(len(table.columns) + 4, len(table.columns) + 4, 23)
        writer.book.close()
        output.seek(0)
        return output

    def get_response(self, output_name='Сводный табель', **kwargs):
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
        return list(
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
