import json, re
from datetime import datetime

from django.db import models
from django.urls import URLPattern, URLResolver
from django.conf import settings
from django.core.exceptions import ValidationError

from src.base import models as qos_models
from src.util.forms import IntegersList


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



def check_func_groups():
    always_allowed_funcs = [
        # old
        'wrapper',
        'is_signed',
        'update_csrf',
        'signin',
        'get_user_allowed_funcs',
        'rotate_fcm_token',
        #rest
        'ShopViewSet',
        'WorkerDayViewSet',
        'UserViewSet',
        'EmploymentViewSet',
        'APIRootView',
        'LoginView',
        'LogoutView',
        'PasswordChangeView',
        'WorkTypeNameViewSet',
        'WorkTypeViewSet',
        'OperationTypeNameViewSet',
        'OperationTypeViewSet',
        'PeriodClientsViewSet',
        'ShopMonthStatViewSet',

        'check_func_groups',
        # 'get_user_month_info',  # in old version
    ]

    def get_all_view_names(all_url_patterns=None, all_views=[]):
        if all_url_patterns is None:  # на 0ом уровне рекурсии
            all_url_patterns = list(filter(
                lambda x: re.match('^api', x.__str__()),
                __import__(settings.ROOT_URLCONF).urls.urlpatterns
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
        if view not in dict(qos_models.FunctionGroup.FUNCS_TUPLE).keys():
            missing_views.append(view)
            # if 'The following' not in error_group_message:
            #     error_group_message = 'The following views are not mentioned in FUNCS list: {}, '.format(view)
            # else:
            #     error_group_message += '{}, '.format(view)
    if missing_views:
        raise ValueError('The following views are not mentioned in FUNCS list: ' + ', '.join(missing_views))
#

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
