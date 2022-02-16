from django_json_widget.widgets import JSONEditorWidget
from django.utils.translation import gettext_lazy as _
from django import forms
from import_export.forms import ImportForm, ConfirmImportForm
from src.base.models import Group

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

    def clean_parent(self):
        parent = self.cleaned_data.get('parent')
        raise_exc_cond = (
            'parent' in self.changed_data and 
            parent and 
            self.instance and
            parent.get_ancestors().filter(pk=self.instance.id).exists()
        )
        if raise_exc_cond:
            self.add_error(
                'parent', 
                _('Shop with id {} may not be parent of shop with id {} because it is his descendant.').format(
                    parent.id,
                    self.instance.id,
                )
            )
        return parent

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
