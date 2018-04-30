import json
from datetime import datetime, timedelta

from django import forms
from django.core.exceptions import ValidationError

from src.db.models import WorkerDay
from src.util import forms as util_forms
from src.util.models_converter import WorkerDayConverter, UserConverter, BaseConverter


class GetCashiersListForm(forms.Form):
    dt_hired_before = util_forms.DateField(required=False)
    dt_fired_after = util_forms.DateField(required=False)
    shop_id = forms.IntegerField(required=False)

    def clean_dt_hired_before(self):
        value = self.cleaned_data.get('dt_hired_before')
        if value is None:
            return (datetime.now() + timedelta(days=10)).date()
        return value

    def clean_dt_fired_after(self):
        value = self.cleaned_data.get('dt_fired_after')
        if value is None:
            return datetime.now().date()
        return value


class GetCashierTimetableForm(forms.Form):
    worker_id = util_forms.IntegersList(required=True)
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    format = util_forms.ChoiceField(['raw', 'excel'], 'raw')

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['from_dt'] > self.cleaned_data['to_dt']:
            raise forms.ValidationError('from_dt have to be less or equal than to_dt')


class GetCashierInfoForm(forms.Form):
    worker_id = forms.IntegerField()
    info = util_forms.MultipleChoiceField(['general_info', 'cashbox_type_info', 'constraints_info', 'work_hours'])


class GetWorkerDayForm(forms.Form):
    worker_id = forms.IntegerField()
    dt = util_forms.DateField()


class SetWorkerDayForm(forms.Form):
    worker_id = forms.IntegerField()
    dt = util_forms.DateField()
    type = forms.CharField()
    tm_work_start = util_forms.TimeField(required=False)
    tm_work_end = util_forms.TimeField(required=False)
    tm_break_start = util_forms.TimeField(required=False)

    cashbox_type = forms.IntegerField(required=False)
    comment = forms.CharField(max_length=128, required=False)

    def clean_type(self):
        value = WorkerDayConverter.parse_type(self.cleaned_data['type'])
        if value is None:
            raise ValidationError('Invalid enum value')
        return value

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['type'] == WorkerDay.Type.TYPE_WORKDAY.value:
            if self.cleaned_data.get('tm_work_start') is None or self.cleaned_data.get('tm_work_end') is None or self.cleaned_data.get('tm_break_start') is None:
                raise ValidationError('tm_work_start, tm_work_end and tm_break_start required')


class SetCashierInfoForm(forms.Form):
    worker_id = forms.IntegerField()
    work_type = forms.CharField(required=False)
    cashbox_info = forms.CharField(required=False)
    constraint = forms.CharField(required=False)
    extra_info = forms.CharField(required=False)

    def clean_work_type(self):
        value = self.cleaned_data.get('work_type')
        if value is None or value == '':
            return None

        value = UserConverter.parse_work_type(value)
        if value is None:
            raise ValidationError('Invalid enum value')
        return value

    def clean_cashbox_info(self):
        try:
            value = self.cleaned_data.get('cashbox_info')
            if value is None or value == '':
                return None
            return json.loads(value)
        except:
            raise ValidationError('Invalid data')

    def clean_constraint(self):
        try:
            value = self.cleaned_data.get('constraint')
            if value is None or value == '':
                return None
            value = json.loads(value)
            value = {int(wd): [BaseConverter.parse_time(x) for x in tms] for wd, tms in value.items()}
        except:
            raise ValidationError('Invalid data')

        for wd in value:
            if wd < 0 or wd > 6:
                raise ValidationError('Invalid week day')

        return value


class CreateCashierForm(forms.Form):
    first_name = forms.CharField(max_length=30)
    middle_name = forms.CharField(max_length=64)
    last_name = forms.CharField(max_length=150)
    username = forms.CharField(max_length=150)
    password = forms.CharField(max_length=64)
    work_type = forms.CharField(max_length=3)
    dt_hired = util_forms.DateField()

    def clean_work_type(self):
        value = self.cleaned_data.get('work_type')
        if value is None or value == '':
            raise ValidationError('Invalid value')

        value = UserConverter.parse_work_type(value)
        if value is None:
            raise ValidationError('Invalid enum value')
        return value


class DeleteCashierForm(forms.Form):
    user_id = forms.IntegerField()
    dt_fired = util_forms.DateField()
