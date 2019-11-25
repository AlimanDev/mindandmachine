from django import forms
from .models import CameraCashboxStat


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


class GetVisitorsInfoForm(forms.Form):
    from_dt = forms.DateField()
    to_dt = forms.DateField()
    shop_id = forms.IntegerField()


