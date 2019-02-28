import json

from django import forms
from django.core.exceptions import ValidationError

from src.util import forms as util_forms
from src.util.models_converter import UserConverter, WorkerDayConverter, BaseConverter


class GetWorkerStatForm(forms.Form):
    shop_id = forms.IntegerField(required=False)
    dt = util_forms.DateField()

    worker_ids = util_forms.IntegersList(required=False)

