from django import forms
from django_json_widget.widgets import JSONEditorWidget
from import_export.forms import ImportForm, ConfirmImportForm

from src.base.models import Group, Network


class CustomSelectWidget(forms.Select):
    template_name = 'select.html'


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
        'shop_default_values',
        'fines_settings',
    ]


class ShopAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'tm_open_dict',
        'tm_close_dict',
        'load_template_settings',
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


class FunctionGroupAdminForm(DefaultOverrideAdminWidgetsForm):
    class Meta:
        widgets = {
            'func': CustomSelectWidget
        }


class CustomImportFunctionGroupForm(ImportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['groups'] = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=True)


class CustomConfirmImportFunctionGroupForm(ConfirmImportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['groups'] = forms.ModelMultipleChoiceField(queryset=Group.objects.all(), required=True)


class CustomImportShopForm(ImportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['network'] = forms.ModelChoiceField(queryset=Network.objects.all(), required=True)


class CustomConfirmImportShopForm(ConfirmImportForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['network'] = forms.ModelChoiceField(queryset=Network.objects.all(), required=True)


class SawhSettingsAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'work_hours_by_months',
    ]


class SawhSettingsMappingAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'work_hours_by_months',
    ]
