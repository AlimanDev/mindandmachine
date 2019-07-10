from django import forms


class SigninForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(max_length=128)


class FCMTokenForm(forms.Form):
    fcm_token = forms.CharField()
    platform = forms.CharField()
