from django import forms
from src.util import forms as util_forms
from src.db.models import OperationTemplate


class GetOperationTemplatesForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    operation_type_id = forms.IntegerField(required=False)


class DeleteOperationTemplateForm(forms.Form):
    id = forms.IntegerField()


class OperationTemplateForm(forms.ModelForm):
    class Meta:
        model = OperationTemplate
        fields = ['name', 'value', 'tm_start', 'tm_end', 'period', 'days_in_period']


class CreateOperationTemplateForm(OperationTemplateForm):
    operation_type_id = forms.IntegerField(required=True)


class UpdateOperationTemplateForm(OperationTemplateForm):
    id = forms.IntegerField(required=True)
    date_rebuild_from = forms.DateField(required=False)
