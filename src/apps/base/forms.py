from django import forms
from django_json_widget.widgets import JSONEditorWidget
from import_export.forms import ImportForm, ConfirmImportForm

from src.apps.base.models import Group, Network


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

    def clean_timesheet_min_hours_threshold(self):
        timesheet_min_hours_threshold = self.data['timesheet_min_hours_threshold']
        if 'timesheet_min_hours_threshold' in self.changed_data:
            timesheet_min_hours_threshold = timesheet_min_hours_threshold.replace(',', '.')
            try:
                self.instance.timesheet_min_hours_threshold = timesheet_min_hours_threshold
                self.instance.get_timesheet_min_hours_threshold(100)
            except Exception as e:
                self.add_error('timesheet_min_hours_threshold', str(e))
        return timesheet_min_hours_threshold


class ShopAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'tm_open_dict',
        'tm_close_dict',
        'load_template_settings',
    ]
    class Meta:
        exclude = ['dttm_deleted']


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
