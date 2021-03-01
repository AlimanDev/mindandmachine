from typing import Type

from rest_framework import serializers


class EventRegistryHolder(type):
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


class BaseRegisteredEvent(metaclass=EventRegistryHolder):
    """
    Any class that will inherits from BaseRegisteredClass will be included
    inside the dict RegistryHolder.REGISTRY, the key being the name of the
    class and the associated value, the class itself.
    """
    code = None
    name = None
    write_history = True

    def __init__(self, network_id, user_author_id, context):
        self.network_id = network_id
        self.user_author_id = user_author_id
        self.context = context

    def __str__(self):
        return self.name

    def __repr__(self):
        return self.__str__()

    def get_recipients(self):
        return []

    def get_file(self):
        return None
