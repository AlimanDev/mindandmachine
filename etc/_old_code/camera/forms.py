from django import forms
from src.db.models import CameraCashboxStat


class CamRequestForm(forms.Form):
    key = forms.CharField()
    data = forms.CharField()


class CameraStatFrom(forms.ModelForm):
    class Meta:
        model = CameraCashboxStat
        fields = [
            'dttm',
            'queue',
        ]

    name = forms.CharField()

