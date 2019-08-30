from django import forms
from src.util import forms as util_forms


class GetOperationTemplatesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    operation_type_id = forms.IntegerField()


class CreateOperationTemplateForm(forms.Form):
    operation_type_id = forms.IntegerField()
    name = forms.CharField(max_length=128)
    value = forms.FloatField()
    tm_start = util_forms.TimeField()
    tm_end = util_forms.TimeField()
    period = util_forms.ChoiceField(choices=['D', 'W', 'M'])
    days_in_period = util_forms.IntegersList()


class DeleteOperationTemplateForm(forms.Form):
    id = forms.IntegerField()


class UpdateOperationTemplateForm(forms.Form):
    id = forms.IntegerField()
    name = forms.CharField(max_length=128)
    value = forms.FloatField()
    tm_start = util_forms.TimeField()
    tm_end = util_forms.TimeField()
    period = util_forms.ChoiceField(choices=['D', 'W', 'M'])
    days_in_period = util_forms.IntegersList()
