from src.apps.base.forms import DefaultOverrideAdminWidgetsForm

class ImportJobForm(DefaultOverrideAdminWidgetsForm):
    json_fields = ['retry_attempts']

class ExportJobForm(DefaultOverrideAdminWidgetsForm):
    json_fields = ['retry_attempts']

