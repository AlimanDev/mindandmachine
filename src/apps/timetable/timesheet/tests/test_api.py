from datetime import date, datetime, time, timedelta
from unittest import mock

import pandas as pd
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status

from src.apps.base.models import Network
from src.apps.base.tests import EmployeeFactory, EmploymentFactory, ShopFactory
from src.apps.timetable.models import TimesheetItem, WorkerDay
from src.apps.timetable.tests.factories import WorkerDayFactory
from src.common.time import DateTimeHelper
from ._base import TestTimesheetMixin


class TestTimesheetApiView(TestTimesheetMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.user_worker)

    def test_get_timesheet_list(self):
        self._calc_timesheets()
        resp = self.client.get(self.get_url('Timesheet-list'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 30)

    def test_get_timesheet_stats(self):
        self._calc_timesheets()
        resp = self.client.get(
            self.get_url('Timesheet-stats'),
            data={
                'dt__gte': date(2021, 6, 1),
                'dt__lte': date(2021, 6, 30),
            },
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        employee_timesheet_stats = resp_data[str(self.employee_worker.id)]
        self.assertDictEqual(employee_timesheet_stats, {
            "fact_total_all_hours_sum": 63.0,
            "fact_total_work_hours_sum": 63.0,
            "fact_day_work_hours_sum": 63.0,
            "fact_night_work_hours_sum": 0.0,
            "main_total_hours_sum": None,
            "main_day_hours_sum": None,
            "main_night_hours_sum": None,
            "additional_hours_sum": None,
            "norm_hours": 167.0,
            "sawh_hours": 167.0,
            "sawh_hours_without_reduce": 167.0
        })

    def test_get_timesheet_stats_with_additional_types(self):
        new_wd_type = self._create_san_day()
        dt = date(2021, 6, 1)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=dt,
            type_id=new_wd_type.code,
            dttm_work_start=datetime.combine(dt, time(10)),
            dttm_work_end=datetime.combine(dt, time(20)),
        )
        self._calc_timesheets()
        resp = self.client.get(
            self.get_url('Timesheet-stats'),
            data={
                'dt__gte': date(2021, 6, 1),
                'dt__lte': date(2021, 6, 30),
            },
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        employee_timesheet_stats = resp_data[str(self.employee_worker.id)]
        self.assertDictEqual(employee_timesheet_stats, {
            "fact_total_all_hours_sum": 72.0,
            "fact_total_work_hours_sum": 63.0,
            "fact_day_work_hours_sum": 63.0,
            "fact_night_work_hours_sum": 0.0,
            "main_total_hours_sum": None,
            "main_day_hours_sum": None,
            "main_night_hours_sum": None,
            "additional_hours_sum": None,
            "norm_hours": 167.0,
            "sawh_hours": 167.0,
            "sawh_hours_without_reduce": 167.0,
            "hours_by_type": {
                "SD": 9.0,
            }
        })

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
        _calc_timesheets_delay.assert_called_once_with(
            employee_id__in=[self.employee_worker.id],
            dt_from='2021-05-01',
            dt_to='2021-05-31',
        )

        employee2 = EmployeeFactory(user=self.user_worker, tabel_code='user_worker_employee2')

        data['employee_id__in'] = [employee2.id]
        resp = self.client.post(
            self.get_url('Timesheet-recalc'), data=self.dump_data(data), content_type='application/json')
        self.assertContains(resp, 'Не найдено сотрудников удовлетворяющих условиям запроса.', status_code=400)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True, CELERY_TASK_EAGER_PROPAGATES=True)
    def test_recalc_timesheet_employee_from_another_shop(self):
        self.add_group_perm(self.group_worker, 'Timesheet_recalc', 'POST')
        dt = date.today()
        emp = EmploymentFactory()
        WorkerDayFactory(
            shop=self.shop,
            dt=dt,
            employee=emp.employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_approved=True,
            is_fact=True
        )
        total = TimesheetItem.objects.filter(employee=emp.employee, shop=self.shop).count()
        data = {
            'shop_id': self.shop.id,
            'dt_from': dt.replace(day=1),
            'dt_to': DateTimeHelper.last_day_in_month(dt),
            'employee_id__in': [emp.employee.id]
        }
        resp = self.client.post(self.get_url('Timesheet-recalc'), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertNotEqual(TimesheetItem.objects.filter(employee=emp.employee, shop=self.shop).count(), total)

    def test_timesheet_lines(self):
        self.add_group_perm(self.group_worker, 'Timesheet_lines', 'GET')
        for dt in pd.date_range('2021-01-01', '2021-01-31').date:
            TimesheetItem.objects.create(
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
                shop=self.shop,
                position=self.position_worker,
                employee=self.employee_worker,
                dt=dt,
                day_type_id=WorkerDay.TYPE_WORKDAY,
                day_hours=8,
            )
            TimesheetItem.objects.create(
                timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
                shop=self.shop,
                position=self.position_worker,
                employee=self.employee_worker,
                dt=dt,
                day_type_id=WorkerDay.TYPE_WORKDAY,
                day_hours=8,
            )
        TimesheetItem.objects.create(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            shop=self.shop,
            position=self.position_worker,
            employee=self.employee_worker,
            dt='2021-01-01',
            day_type_id=WorkerDay.TYPE_QUALIFICATION,
            day_hours=4,
        )
        TimesheetItem.objects.create(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            shop=self.shop,
            position=self.position_worker,
            employee=self.employee_worker,
            dt='2021-01-01',
            day_type_id=WorkerDay.TYPE_WORKDAY,
            night_hours=4,
        )

        resp = self.client.get(self.get_url('Timesheet-lines'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 2)

    def test_timesheet_lines_group_by_employee_and_position(self):
        self.network.api_timesheet_lines_group_by = Network.TIMESHEET_LINES_GROUP_BY_EMPLOYEE_POSITION
        self.network.save()
        shop2 = ShopFactory(
            parent=self.root_shop,
            name='SHOP_NAME2',
            network=self.network,
            email='shop2@example.com',
            settings__breaks=self.breaks,
        )

        self.add_group_perm(self.group_worker, 'Timesheet_lines', 'GET')
        TimesheetItem.objects.create(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_FACT,
            shop=self.shop,
            position=self.position_worker,
            employee=self.employee_worker,
            dt='2021-01-01',
            day_type_id=WorkerDay.TYPE_WORKDAY,
            day_hours=8,
        )
        TimesheetItem.objects.create(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
            shop=self.shop,
            position=self.position_worker,
            employee=self.employee_worker,
            dt='2021-01-01',
            day_type_id=WorkerDay.TYPE_WORKDAY,
            day_hours=8,
        )
        TimesheetItem.objects.create(
            timesheet_type=TimesheetItem.TIMESHEET_TYPE_MAIN,
            shop=shop2,
            position=self.position_worker,
            employee=self.employee_worker,
            dt='2021-01-01',
            day_type_id=WorkerDay.TYPE_WORKDAY,
            day_hours=3,
        )

        resp = self.client.get(self.get_url('Timesheet-lines'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 2)
        self.assertEqual(len(resp_data[0]['days']), 1)
        self.assertNotIn('shop_id', resp_data[0])
        self.assertNotIn('shop__code', resp_data[0])
