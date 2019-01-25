import datetime
import json

from django import forms
from django.core.exceptions import ValidationError

from src.util.dict import DictUtil
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


class RangeField(forms.CharField):
    def __init__(self, required=False, **kwargs):
        kwargs['required'] = required
        super().__init__(**kwargs)

    def clean(self, value, **kwargs):
        value = super().clean(value)

        if value is None or len(value) < 3:
            if self.required:
                raise ValidationError('required range from-to')
            return []

        if '-' not in value:
            raise ValidationError('unsatisfied range form, should be from-to')

        value = value.split('-')

        if len(value) != 2:
            raise ValidationError('there should be 2 numbers')
        try:
            from_value = int(value[0])
            to_value = int(value[1])
        except ValueError:
            raise ValidationError('first or second value is not a number')

        # is_percents = kwargs.pop('is_percents', None)
        # if is_percents:
        #     if not 0 <= from_value <= 100:
        #         raise ValidationError('first value should be in range 0-100')
        #     if not 0 <= to_value <= 100:
        #         raise ValidationError('second value should be in range 0-100')

        return from_value, to_value


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


class FormUtil(object):
    @staticmethod
    def get_shop_id(request, form):
        return DictUtil.get_not_none(form, 'shop_id', request.user.shop_id)

    @staticmethod
    def get_dt_from(form):
        return DictUtil.get_not_none(form, 'from_dt', datetime.date(year=1971, month=1, day=1))

    @staticmethod
    def get_checkpoint(form):
        return DictUtil.get_not_none(form, 'checkpoint', 1)

    @staticmethod
    def get_dt_to(form):
        return DictUtil.get_not_none(form, 'to_dt', datetime.date(year=2037, month=1, day=1))
