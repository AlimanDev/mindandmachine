from django import forms

from src.base.forms import CustomSelectWidget

class ReportConfigForm(forms.ModelForm):
    class Meta:
        widgets = {
            'report_type': CustomSelectWidget,
            'cron': CustomSelectWidget,
            'period': CustomSelectWidget,
        }
