from django import forms
import src.util.forms as util_forms


class GetUserUrvForm(forms.Form):
    worker_ids = util_forms.IntegersList()
    from_dt = util_forms.DateField()
    to_dt = util_forms.DateField()
    shop = forms.IntegerField(required=False)
    offset = forms.IntegerField(required=False)

    from_tm = util_forms.TimeField(required=False)
    to_tm = util_forms.TimeField(required=False)
    show_not_verified = forms.BooleanField(required=False)
    show_not_detected = forms.BooleanField(required=False)
    show_workers = forms.BooleanField(required=False)
    show_outstaff = forms.BooleanField(required=False)


class ChangeAttendanceForm(forms.Form):
    attendance_id = forms.IntegerField()
    to_user_id = forms.IntegerField(required=False)
    is_outsource = forms.BooleanField(required=False)