import xlsxwriter
import io

from django.conf import settings
from django.contrib.auth import authenticate, login
from django.http import HttpResponse
from src.util.utils import JsonResponse


def get_table(request):
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    # workbook = xlsxwriter.Workbook('hello.xlsx')
    worksheet = workbook.add_worksheet()


    workbook.close()
    output.seek(0)

    response = HttpResponse(
        output,
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = 'attachment; filename="Tablet_{}.xlsx"'.format(BaseConverter.convert_date(weekday))

    return response



def xlsx_method(func):
    def wrapper(request, *args, **kwargs):
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        name = func(request, workbook, *args, **kwargs)
        workbook.close()
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="{}.xlsx"'.format(name)
        return response
    return wrapper
