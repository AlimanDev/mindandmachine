from src.util.utils import api_method
from .utils import get_uploaded_file, upload_vacation_util, upload_demand_util, upload_timetable_util
from .forms import UploadForm


@api_method('POST', UploadForm)
@get_uploaded_file
def upload_demand(request, form, demand_file):
    """
    Принимает от клиента экселевский файл в формате из TPNET (для леруа специально) и загружает из него данные в бд

    Args:
         method: POST
         url: /api/upload/upload_demand
         shop_id(int): required = True
    """
    return upload_demand_util(demand_file)


@api_method('POST', UploadForm)
@get_uploaded_file
def upload_timetable(request, form, timetable_file):
    """
    Принимает от клиента экселевский файл и создает расписание (на месяц)

    Args:
         method: POST
         url: /api/upload/upload_timetable
         shop_id(int): required = True
    """
    return upload_timetable_util(form, timetable_file)


@api_method('POST')
@get_uploaded_file
def upload_vacation(request, vacation_file):
    """
    Принимает от клиента экселевский файл и загружает отпуска

    Args:
         method: POST
    """
    return upload_vacation_util(vacation_file)

