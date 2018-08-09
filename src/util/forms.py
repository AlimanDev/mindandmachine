import datetime
import json

from django import forms
from django.core.exceptions import ValidationError

from src.db.models import Shop

from src.util.dict import DictUtil
from src.util.models_converter import PeriodDemandConverter
from src.conf.djconfig import (
    QOS_DATE_FORMAT,
    QOS_DATETIME_FORMAT,
    QOS_TIME_FORMAT,
)


class DateField(forms.DateField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=(QOS_DATE_FORMAT,),
            **kwargs
        )


class TimeField(forms.TimeField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=(QOS_TIME_FORMAT,),
            **kwargs
        )


class DatetimeField(forms.DateTimeField):
    def __init__(self, **kwargs):
        super().__init__(
            input_formats=(QOS_DATETIME_FORMAT,),
            **kwargs
        )


class ChoiceField(forms.ChoiceField):
    def __init__(self, choices, default=None, **kwargs):
        self.default = default
        if default is not None:
            kwargs['required'] = False

        super().__init__(
            choices=((x, '') for x in choices),
            **kwargs
        )

    def clean(self, value):
        result = super().clean(value)
        if result is None and self.default is not None:
            result = self.default
        return result


class MultipleChoiceField(forms.MultipleChoiceField):
    def __init__(self, choices, default=None, **kwargs):
        self.default = default
        if default is not None:
            kwargs['required'] = False

        super().__init__(
            choices=((x, '') for x in choices),
            **kwargs
        )

    def to_python(self, value):
        value = super().to_python(value)
        result = []
        for x in value:
            result += x.split(',')
        return result

    def clean(self, value):
        value = super().clean(value)
        if value is None and self.default is not None:
            value = self.default
        return value


class BooleanField(forms.BooleanField):
    def __init__(self, required=False):
        super().__init__(required=required)


class IntegersList(forms.CharField):
    def __init__(self, required=False, **kwargs):
        kwargs['required'] = required
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)

        if value is None or value == '':
            if self.required:
                raise ValidationError('required IntegerListType')
            return []

        try:
            value = json.loads(value)
        except:
            raise ValidationError('invalid IntegerListType')

        if not isinstance(value, list):
            raise ValidationError('invalid IntegerListType')

        if self.required and len(value) <= 0:
            raise ValidationError('IntegerListType cannot be empty')

        for x in value:
            if not isinstance(x, int):
                raise ValidationError('invalid IntegerListType')

        return value


class PeriodDemandForecastType(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def clean(self, value):
        value = super().clean(value)
        value = PeriodDemandConverter.parse_forecast_type(value)
        if value is None:
            raise ValidationError('invalid PeriodDemandForecastType')

        return value


class FormUtil(object):
    @staticmethod
    def get_shop_id(request, form):
        try:
            shop_id = Shop.objects.get(id=form['shop_id']).id
        except Shop.DoesNotExist:
            shop_id = request.user.shop_id
        return shop_id

    @staticmethod
    def get_dt_from(form):
        return DictUtil.get_not_none(form, 'from_dt', datetime.date(year=1971, month=1, day=1))

    @staticmethod
    def get_dt_to(form):
        return DictUtil.get_not_none(form, 'to_dt', datetime.date(year=2037, month=1, day=1))
