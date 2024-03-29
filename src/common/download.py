from django.utils.encoding import escape_uri_path
import pandas as pd
import io
from functools import wraps
from django.http.response import HttpResponse


def xlsx_method(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        output = io.BytesIO()
        workbook = pd.ExcelWriter(output, engine='xlsxwriter') # TODO: move to openpyxl
        workbook, name = func(request, workbook, *args, **kwargs)

        if name != 'error':
            workbook.close()
            output.seek(0)

            response = HttpResponse(
                output,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(escape_uri_path(name))
        else:
            response = workbook

        return response
    return wrapper