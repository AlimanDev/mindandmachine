from django import forms
from src.util import forms as util_forms


class GetCashboxesInfo(forms.Form):
    shop_id = forms.IntegerField()
    checkpoint = forms.IntegerField(required=False)


class GetCashiersInfo(forms.Form):
    shop_id = forms.IntegerField()
    dttm = util_forms.DatetimeField()


class ChangeCashierStatus(forms.Form):
    shop_id = forms.IntegerField()
    worker_id = forms.IntegerField()
    status = forms.CharField()
    cashbox_id = forms.IntegerField(required=False)
    is_current_time = util_forms.BooleanField()  # True: current time, False: timetable time
    tm_changing = util_forms.TimeField(required=False)

    # случай когда сажаем человека не из расписания
    # ситуация: заболел человек звонят рандомному сотруднику, просят выйти за место заболевшего
    # но изначально неизвестно какое расписание было у заболевшего

    tm_work_end = util_forms.TimeField(required=False)
