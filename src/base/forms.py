from django_json_widget.widgets import JSONEditorWidget
from django import forms
from import_export.forms import ImportForm, ConfirmImportForm
from src.base.models import Group

class DefaultOverrideAdminWidgetsForm(forms.ModelForm):
    json_fields = []
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.json_fields:
            self.fields[field].widget = JSONEditorWidget()


class NetworkAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'settings_values',
        'worker_position_default_values',
    ]


class ShopAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'tm_open_dict',
        'tm_close_dict',
    ]


class ShopSettingsAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'method_params',
        'cost_weights',
        'init_params',
    ]


class BreakAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'value',
    ]


class CustomImportFunctionGroupForm(ImportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'] = forms.ModelChoiceField(queryset=Group.objects.all(), required=True)

class CustomConfirmImportFunctionGroupForm(ConfirmImportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['group'] = forms.ModelChoiceField(queryset=Group.objects.all(), required=True)
