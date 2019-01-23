from src.db.models import (
    User,
    Slot,
    UserWeekdaySlot,
    CashboxType,
    Region,
)
from src.util.forms import FormUtil
from src.util.models_converter import (
    BaseConverter,
    SlotConverter
)
from src.util.utils import api_method, JsonResponse
from .forms import (
    GetSlots,
    GetAllSlots,
    SetSlot,
    CreateSlotForm,
    DeleteSlotForm
)
from collections import defaultdict


@api_method('GET', auth_required=False, check_permissions=False)
def get_regions(request):
    return JsonResponse.success(list(Region.objects.all().values_list('title', flat=True)))


@api_method('GET', GetAllSlots)
def get_all_slots(request, form):
    """
    Возвращает список слотов в магазине

    Args:
        method: GET
        url: api/other/get_all_slots
        shop_id(int): required = True

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
    slots = Slot.objects.filter(shop=form['shop_id'])
    for slot in slots:
        result.append({
            'id': slot.id,
            'name': slot.name,
            'tm_start': BaseConverter.convert_time(slot.tm_start),
            'tm_end': BaseConverter.convert_time(slot.tm_end),
        })
    return JsonResponse.success({
        'slots': result,
    })


@api_method('POST', SetSlot, lambda_func=lambda x: User.objects.filter(id=x['user_id']).first())
def set_slot(request, form):
    """

    Args:
        method: POST
        url: api/other/set_slot
        slots(str): список слотов (вроде)
        user_id(int):

    Returns:
        JsonResponse.success

    Raises:
        JsonResponse.value_error

    """
    # weekday = form['weekday']
    try:
        user = User.objects.get(id=form['user_id'])
    except User.DoesNotExist:
        return JsonResponse.does_not_exists_error('user_id')

    shop_slots = Slot.objects.filter(shop_id=user.shop_id).values_list('id', flat=True)

    slots_list = []
    bad_slot = False
    for wd, slot_ids in form['slots'].items():
        for slot_id in slot_ids:
            if slot_id in shop_slots:
                slots_list.append(
                    UserWeekdaySlot(
                        worker=user,
                        weekday=wd,
                        slot_id=slot_id,
                    )
                )
            else:
                bad_slot =True
                break
        if bad_slot:
            break

    if not bad_slot:
        UserWeekdaySlot.objects.filter(worker=user).delete()
        UserWeekdaySlot.objects.bulk_create(slots_list)
        return JsonResponse.success()
    return JsonResponse.value_error('there is no slot with id {} in the shop (id {})'.format(slot_id, user.shop_id))


@api_method('GET', GetSlots)
def get_slots(request, form):
    """

    Args:
        method: GET
        url: api/other/get_slots
        user_id(int): required = True
        shop_id(int): required = False

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
            'id': ws.slot.id,
            'name': ws.slot.name,
            'tm_start': BaseConverter.convert_time(ws.slot.tm_start),
            'tm_end': BaseConverter.convert_time(ws.slot.tm_end),
        })

    return JsonResponse.success({
        'slots': slots_by_weekday,
    })


@api_method(
    'POST',
    CreateSlotForm,
    lambda_func=lambda x: CashboxType.objects.get(id=x['cashbox_type_id']).shop
)
def create_slot(request, form):
    """
    Создает новый слов

    Args:
        method: POST
        url: /api/other/create_slot
        cashbox_type_id(int): required = True
        tm_start(QOS_TIME): required = True
        tm_end(QOS_TIME): required = True

    Returns:
        {
            | 'id': id созданного слота,
            | 'shop': id shop'a,
            | 'tm_start': tm_start,
            | 'tm_end':  tm_end,
            | 'name': название слота
        }

    Raises:
        JsonResponse.already_exists_error: если слот с таким cashbox_type_id и временами уже существует
    """
    shop_id = FormUtil.get_shop_id(request, form)

    slot_dict = {
        'shop_id': shop_id,
        'cashbox_type_id': form['cashbox_type_id'],
        'tm_start': form['tm_start'],
        'tm_end': form['tm_end']
    }

    is_exist = Slot.objects.filter(**slot_dict)
    if is_exist.count() > 0:
        return JsonResponse.already_exists_error('such slot already exists')

    new_slot = Slot.objects.create(**slot_dict)

    return JsonResponse.success(SlotConverter.convert(new_slot))


@api_method(
    'POST',
    DeleteSlotForm,
    lambda_func=lambda x: Slot.objects.get(id=x['slot_id']).shop
)
def delete_slot(request, form):
    """
    Warning:
        Напрямую удаляет слот из бд(без всякого проставления dttm_deleted или чего-то еще)

    Args:
        method: POST
        url: /api/other/delete_slot
        slot_id(int): required = True
    """
    Slot.objects.get(id=form['slot_id']).delete()

    return JsonResponse.success('slot was successfully deleted')
