from django import forms


class UploadForm(forms.Form):
    shop_id = forms.IntegerField()
