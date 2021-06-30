from django.test import override_settings
from rest_framework.test import APITestCase

from ._base import TestTimesheetMixin


@override_settings(FISCAL_SHEET_DIVIDER_ALIAS=None)
class TestTimesheetApiView(TestTimesheetMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.user_worker)

    def test_get_timesheet_list(self):
        self._calc_timesheets()
        resp = self.client.get(self.get_url('Timesheet-list'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 30)
