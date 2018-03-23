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


# time format hhmm, for example : 745 (7:45), 2300 (23:00)
class DayTimeField(models.SmallIntegerField):
    pass


class Enum(enum.Enum):
    @classmethod
    def is_valid(cls, value):
        for x in cls:
            if x.value == value:
                return True
        return False
