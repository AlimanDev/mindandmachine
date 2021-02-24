from src.base.forms import DefaultOverrideAdminWidgetsForm


class LoadTemplateAdminForm(DefaultOverrideAdminWidgetsForm):
    json_fields = [
        'forecast_params',
    ]
