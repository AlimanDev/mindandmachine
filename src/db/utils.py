from django.db import models
import enum
from . import models as db_models
from django.urls import URLPattern, URLResolver
from django.conf import settings


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


def check_func_groups():
    always_allowed_funcs = ['wrapper', 'is_signed', 'update_csrf', 'signin', 'get_user_allowed_funcs']

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
        raise ValueError('The following views are not mentioned in FUNCS list: ' + ', '.join(missing_views)[:-2])

