from django import forms

from src.base.forms import CustomSelectWidget

class GenericExternalCodeForm(forms.ModelForm):
    class Meta:
        widgets = {
            'object_type': CustomSelectWidget
        }

class ShopExternalCodeForm(forms.ModelForm):
    class Meta:
        widgets = {
            'attendance_area': CustomSelectWidget
        }
