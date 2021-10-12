from django import forms
from src.base.forms import CustomSelectWidget

class EventEmailNotificationForm(forms.ModelForm):
    select_change_fields = ['event_type']
    class Meta:
        widgets = {
            'event_type': CustomSelectWidget,
            'system_email_template': CustomSelectWidget,
        }
