from django import forms
from django.core.exceptions import ValidationError

from src.db.models import WorkerDay
from src.util import forms as util_forms
from src.util.models_converter import WorkerDayConverter


class GetCashiersSetForm(forms.Form):
    shop_id = forms.IntegerField()


class GetCashierTimetableForm(forms.Form):
    worker_id = forms.IntegerField()
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
    info = util_forms.MultipleChoiceField(['general_info', 'cashbox_type_info', 'constraints_info'])


class SetWorkerDayForm(forms.Form):
    worker_id = forms.IntegerField()
    dt = util_forms.DateField()
    type = forms.CharField()
    tm_work_start = util_forms.TimeField(required=False)
    tm_work_end = util_forms.TimeField(required=False)
    tm_break_start = util_forms.TimeField(required=False)

    def clean_type(self):
        value = WorkerDayConverter.parse_type(self.cleaned_data['type'])
        if value is None:
            raise ValidationError('Invalid enum value')
        return value

    def clean(self):
        if self.errors:
            return

        if self.cleaned_data['type'] == WorkerDay.Type.TYPE_WORKDAY:
            if self.cleaned_data.get('tm_work_start') is None or self.cleaned_data.get('tm_work_end') is None or self.cleaned_data.get('tm_break_start') is None:
                raise ValidationError('tm_work_start, tm_work_end and tm_break_start required')
