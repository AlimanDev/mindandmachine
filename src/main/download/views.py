from src.util.utils import api_method, JsonResponse
from .utils import xlsx_method


@api_method('GET')
@xlsx_method
def get_tabel(request, workbook):
    worksheet = workbook.add_worksheet()
    return 'tmp'




