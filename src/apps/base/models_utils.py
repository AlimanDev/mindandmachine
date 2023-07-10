import json, re
from datetime import datetime

from django.db import models
from django.urls import URLPattern, URLResolver
from django.conf import settings
from django.core.exceptions import ValidationError

from src.apps.base import models as qos_models
from src.common.forms import IntegersList


class IntegerListField(models.TextField):

    def get_prep_value(self, value):
        if value is None:
            return
        if not isinstance(value, list):
            raise ValidationError('invalid IntegerListType')
        return json.dumps(value)

    def from_db_value(self, value, expression, connection, context=None):
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


class OverrideBaseManager:
    prev_managers = {}
    models = []
    manager = None

    def __init__(self, models, manager='objects'):
        self.models = models
        self.manager = manager
        for model in models:
            self.prev_managers[model.__name__] = getattr(model._meta, 'base_manager_name', None)
          
    def __enter__(self):
        for model in self.models:
            model._meta.base_manager_name = self.manager
            if "base_manager" in model._meta.__dict__:
                del model._meta.__dict__["base_manager"]
        return self
      
    def __exit__(self, exc_type, exc_value, exc_traceback):
        for model in self.models:
            prev_manager = self.prev_managers.get(model.__name__)
            model._meta.base_manager_name = prev_manager
            if "base_manager" in model._meta.__dict__:
                del model._meta.__dict__["base_manager"]

def current_year():
    return datetime.now().year
