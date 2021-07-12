from datetime import date
from unittest import mock

from django.test import override_settings
from rest_framework.test import APITestCase

from src.base.tests.factories import EmployeeFactory
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

    @mock.patch('src.timetable.timesheet.tasks.calc_timesheets.delay')
    def test_recalc_timesheet(self, _calc_timesheets_delay):
        self.add_group_perm(self.group_worker, 'Timesheet_recalc', 'POST')
        data = {
            'shop_id': self.employment_worker.shop_id,
            'employee_id__in': [self.employee_worker.id],
            'dt_from': date(2021, 5, 1),
            'dt_to': date(2021, 5, 31),
        }
        self.client.post(
            self.get_url('Timesheet-recalc'), data=self.dump_data(data), content_type='application/json')
        _calc_timesheets_delay.assert_called_once_with(employee_id__in=[self.employee_worker.id])

        employee2 = EmployeeFactory(user=self.user_worker, tabel_code='user_worker_employee2')

        data['employee_id__in'] = [employee2.id]
        resp = self.client.post(
            self.get_url('Timesheet-recalc'), data=self.dump_data(data), content_type='application/json')
        self.assertContains(resp, 'Не найдено сотрудников удовлетворяющих условиям запроса.', status_code=400)
