from src.base.models import (
    FunctionGroup,
)
from src.timetable.models import (
    Slot,
    UserWeekdaySlot,
    WorkType,
)
from src.util.models_converter import Converter
from src.util.utils import api_method, JsonResponse
from .forms import (
    GetSlots,
    GetAllSlots,
    UserAllowedFuncsForm,
)
from collections import defaultdict


@api_method('GET', UserAllowedFuncsForm, check_permissions=False)
def get_user_allowed_funcs(request, form):
    allowed_functions = FunctionGroup.objects.filter(group__employment__user_id=form['worker_id'])
    return JsonResponse.success([
        {
            'name': x.func,
            'access_type': x.access_type
        } for x in allowed_functions
    ])


@api_method('GET', GetAllSlots)
def get_all_slots(request, form):
    """
    Возвращает список слотов в магазине (или на типе работ)

    Args:
        method: GET
        url: api/other/get_all_slots
        shop_id(int): required = True
        work_type_id(int): required = False

    Returns:
        {
            'slots': [
                {
                    | 'id': id слота,
                    | 'tm_start': время начала,
                    | 'tm_end': время конца,
                    | 'name': имя (может быть null)
                }, ...
            ]
        }

    """
    result = []
    if form['work_type_id']:
        slots = Slot.objects.filter(
            work_type__in=WorkType.objects.filter(id=form['work_type_id'])
        )
    else:
        slots = Slot.objects.filter(shop_id=form['shop_id'])
    for slot in slots.filter(dttm_deleted__isnull=True):
        result.append({
            'id': slot.id,
            'name': slot.name,
            'tm_start': Converter.convert_time(slot.tm_start),
            'tm_end': Converter.convert_time(slot.tm_end),
            'work_type_id': slot.work_type.id if slot.work_type else None,
        })
    return JsonResponse.success(result)


@api_method(
    'GET',
    GetSlots,
)
def get_slots(request, form):
    """

    Args:
        method: GET
        url: api/other/get_slots
        user_id(int): required = True

    Returns:

    """
    weekday_slots = UserWeekdaySlot.objects.select_related(
        'slot'
    ).filter(
        worker_id=form['user_id']
    )

    slots_by_weekday = defaultdict(list)
    for ws in weekday_slots:
        slots_by_weekday[ws.weekday].append({
            'slot_id': ws.slot.id,
            'is_suitable': ws.is_suitable,
            'name': ws.slot.name,
            'tm_start': Converter.convert_time(ws.slot.tm_start),
            'tm_end': Converter.convert_time(ws.slot.tm_end),
        })

    return JsonResponse.success(slots_by_weekday)
