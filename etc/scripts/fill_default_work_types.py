from src.base.models import (
    WorkerPosition,
    Network,
)
from src.timetable.models import (
    WorkTypeName,
)


def set_position_default_work_type_names(position_to_work_types_mapping: dict, network=None):
    """

    :param position_to_work_types_mapping:
    Пример:
    {
        r'(.*)?врач(.*)?': ('0001', '0002'),
        r'(.*)?кассир(.*)?': ('0003',),
    }
    :param network: сеть, по умолчанию берется первая
    :return:
    """
    network = network or Network.objects.first()
    for pattern, work_type_codes in position_to_work_types_mapping.items():
        work_type_names_qs = WorkTypeName.objects.filter(
            code__in=work_type_codes,
            network=network,
        )
        for worker_position in WorkerPosition.objects.filter(name__iregex=pattern):
            worker_position.default_work_type_names.set(work_type_names_qs)
