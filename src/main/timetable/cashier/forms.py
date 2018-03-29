from django import forms
from src.util import forms as util_forms


class GetCashiersSetForm(forms.Form):
    shop_id = forms.IntegerField()


class GetCashierTimetableForm(forms.Form):
    worker_id = forms.IntegerField()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    format = util_forms.ChoiceField(['raw', 'excel'], 'raw')

    def format_clean(self):
        super().format_clean()
        if self.cleaned_data.get('format') is None:
            self.cleaned_data['format'] = 'raw'

    def clean(self):
        super().clean()

        if self.cleaned_data['from_dt'] > self.cleaned_data['to_dt']:
            raise forms.ValidationError('from_dt have to be less or equal than to_dt')


class GetCashierInfoForm(forms.Form):
    worker_id = forms.IntegerField()
    info = util_forms.MultipleChoiceField(['general_info', 'cashbox_type_info', 'constraints_info'])
