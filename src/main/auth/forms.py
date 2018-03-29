from django import forms
from src.util import forms as util_forms


class SigninForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(max_length=128)
