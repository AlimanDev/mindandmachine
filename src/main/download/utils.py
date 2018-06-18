import xlsxwriter
import io

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import HttpResponse
from src.util.utils import JsonResponse


def xlsx_method(func):
    def wrapper(request, *args, **kwargs):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        workbook, name = func(request, workbook, *args, **kwargs)
        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(name)
        return response
    return wrapper
