from django.db import models
import enum


class EnumField(models.IntegerField):
    def __init__(self, to_enum, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.enum = to_enum

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        kwargs['to_enum'] = self.enum
        return name, path, args, kwargs


class Enum(enum.Enum):
    @classmethod
    def is_valid(cls, value):
        for x in cls:
            if x.value == value:
                return True
        return False

    @classmethod
    def get_name_by_value(cls, value):
        for x in cls:
            if x.value == value:
                return x
        return None

    @classmethod
    def values(cls):
        return [x.value for x in cls]
