from src.base.models import Shop
from src.forecast.models import OperationType, OperationTypeName
from src.timetable.models import WorkType, WorkTypeName


def create_work_types_and_operations(shop_ids: list, wtn_codes_with_otn_codes):
    """
    Создание типов работ и типов операций

    Пример для Ортеки:
    from etc.scripts.fill.work_types import create_work_types_and_operations
    shop_ids=[84]
    wtn_codes_with_otn_codes = [
        ('doctor', 'doctor'),
        ('consult', 'consult'),
        ('other', 'other'),
        (None, 'bills'),
        (None, 'clients'),
        (None, 'income'),
    ]
    create_work_types_and_operations(shop_ids, wtn_codes_with_otn_codes)
    """
    for shop in Shop.objects.filter(id__in=shop_ids, network__isnull=False).select_related('network'):
        for wtn_code, otn_code in wtn_codes_with_otn_codes:
            work_type = None
            if wtn_code:
                wtn = WorkTypeName.objects.filter(
                    network=shop.network, code=wtn_code).first()
                if wtn:
                    work_type, _wt_created = WorkType.objects.get_or_create(
                        shop=shop, work_type_name=wtn)
            if otn_code:
                otn = OperationTypeName.objects.filter(
                    network=shop.network, code=otn_code).first()
                if otn:
                    op_type, _ot_created = OperationType.objects.get_or_create(
                        shop=shop,
                        operation_type_name=otn,
                        defaults=dict(
                            work_type=work_type,
                        )
                    )
