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



def check_func_groups():
    always_allowed_funcs = [
        'wrapper',
        'is_signed',
        'update_csrf',
        'signin',
        'get_user_allowed_funcs',
        'rotate_fcm_token',
    ]

    def get_all_view_names(all_url_patterns=None, all_views=[]):
        if all_url_patterns is None:  # на 0ом уровне рекурсии
            all_url_patterns = list(filter(
                lambda x: 'api' in x.__str__(),
                __import__(settings.ROOT_URLCONF).main.urls.urlpatterns
            ))  # интересует только /api

        for pattern in all_url_patterns:
            if isinstance(pattern, URLResolver):
                get_all_view_names(pattern.url_patterns, all_views)
            elif isinstance(pattern, URLPattern):
                view_name = pattern.callback.__name__
                if view_name not in always_allowed_funcs:
                    all_views.append(view_name)

        return list(set(all_views))

    all_views_names = get_all_view_names()
    missing_views = []
    for view in all_views_names:
        if view not in db_models.FunctionGroup.FUNCS:
            missing_views.append(view)
            # if 'The following' not in error_group_message:
            #     error_group_message = 'The following views are not mentioned in FUNCS list: {}, '.format(view)
            # else:
            #     error_group_message += '{}, '.format(view)
    if missing_views:
        raise ValueError('The following views are not mentioned in FUNCS list: ' + ', '.join(missing_views))

