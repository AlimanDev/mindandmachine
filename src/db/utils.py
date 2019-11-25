from django.db import models
import enum
from . import models as db_models
from django.urls import URLPattern, URLResolver
from django.conf import settings

import json
from src.util.forms import IntegersList
from django.core.exceptions import ValidationError


class IntegerListField(models.TextField):

    def get_prep_value(self, value):
        if value is None:
            return
        if not isinstance(value, list):
            raise ValidationError('invalid IntegerListType')
        return json.dumps(value)

    def from_db_value(self, value, expression, connection, context):
        if value is None:
            return value
        value = json.loads(value)
        if not isinstance(value, list):
            raise ValidationError('invalid IntegerListType')
        return value

    def to_python(self, value):
        if type(value) == list:
            return value

        return json.loads(value)

    def formfield(self, **kwargs):
        # This is a fairly standard way to set up some defaults
        # while letting the caller override them.
        defaults = {'form_class': IntegersList}
        defaults.update(kwargs)
        return super(IntegerListField, self).formfield(**defaults)

    def clean(self, value, model_instance):
        value = super().clean(value, model_instance)

        if not isinstance(value, list):
            raise ValidationError('invalid IntegerListType')

        if not self.blank and len(value) <= 0:
            raise ValidationError('IntegerListType cannot be empty')

        for x in value:
            if not isinstance(x, int):
                raise ValidationError('invalid IntegerListType')

        return value


