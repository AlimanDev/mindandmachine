from typing import Iterable, Union
from django.utils.functional import cached_property
from django.db.models import QuerySet

class ReportRegistryHolder(type):
    registry = {}

    def __new__(cls, name, bases, attrs):
        new_cls = type.__new__(cls, name, bases, attrs)
        """
        Here the name of the class is used as key but it could be any class
        parameter.
        """
        event_code = getattr(new_cls, 'code', None)
        if event_code:
            cls.registry[event_code] = new_cls
        return new_cls

    @classmethod
    def get_registry(cls):
        return dict(cls.registry)


class BaseRegisteredReport(metaclass=ReportRegistryHolder):
    """
    Any class that will inherits from BaseRegisteredClass will be included
    inside the dict RegistryHolder.REGISTRY, the key being the name of the
    class and the associated value, the class itself.
    """
    code = None
    name = None

    def __init__(self, network_id, context):
        self.network_id = network_id
        self.context = context

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    def get_file(self) -> dict:
        '''
        Final report file

        return:
            {
                'name': str,            # filename
                'file': io.BytesIO(),
                'type': str,            # example: 'application/xlsx',
            }
        '''
        return None

    def get_recipients_shops(self) -> Iterable[int]:
        'Iterable (list, set etc.) of shop_id that this report will be sent to'
        return []

    @cached_property
    def report_data(self) -> Union[QuerySet, list]:
        return None
