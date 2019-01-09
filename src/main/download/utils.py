import xlsxwriter
import io

from django.http import HttpResponse
from functools import wraps


def xlsx_method(func):
    @wraps(func)
    def wrapper(request, *args, **kwargs):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        workbook, name = func(request, workbook, *args, **kwargs)

        if name != 'error':
            workbook.close()
            output.seek(0)

            response = HttpResponse(
                output,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(name)
        else:
            response = workbook

        return response
    return wrapper
