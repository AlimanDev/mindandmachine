import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms
from src.util.models_converter import UserConverter, WorkerDayConverter, BaseConverter


class SelectCashiersForm(forms.Form):
    cashbox_types = util_forms.IntegersList()
    cashier_ids = util_forms.IntegersList()
    work_types = forms.CharField(required=False)
    workday_type = forms.CharField(required=False)
    workdays = forms.CharField(required=False)
    shop_id = forms.IntegerField(required=False)
    checkpoint = forms.IntegerField(required=False)

    work_workdays = forms.CharField(required=False)
    from_tm = util_forms.TimeField(required=False)
    to_tm = util_forms.TimeField(required=False)

    def clean_work_types(self):
        value = self.cleaned_data['work_types']
        if value is None or value == '':
            return []

        try:
            value = json.loads(value)
        except:
            raise ValidationError('invalid')

        value = [UserConverter.parse_work_type(x) for x in value]
        if None in value:
            raise ValidationError('invalid')

        return value

    def clean_workday_type(self):
        value = self.cleaned_data['workday_type']
        if value is None or value == '':
            return None

        value = WorkerDayConverter.parse_type(value)
        if value is None:
            raise ValidationError('invalid')

        return value

    def clean_workdays(self):
        value = self.cleaned_data['workdays']
        if value is None or value == '':
            return []

        try:
            value = json.loads(value)
            value = [BaseConverter.parse_date(x) for x in value]
        except:
            raise ValidationError('invalid')

        return value

    def clean_work_workdays(self):
        value = self.cleaned_data['work_workdays']
        if value is None or value == '':
            return []

        try:
            value = json.loads(value)
            value = [BaseConverter.parse_date(x) for x in value]
        except:
            raise ValidationError('invalid')

        return value

    def clean(self):
        has_wds = len(self.cleaned_data['workdays']) > 0
        has_wd_type = self.cleaned_data['workday_type'] is not None

        if has_wds and not has_wd_type:
            raise ValidationError('workday_type have to be set')


class GetWorkerStatForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    dt = util_forms.DateField()

    worker_ids = util_forms.IntegersList(required=False)

