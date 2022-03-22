from datetime import date, datetime, time
from unittest import mock
from freezegun import freeze_time

from django.test import override_settings
from django.db import transaction
from rest_framework.test import APITestCase

from src.base.tests.factories import EmployeeFactory, EmploymentFactory, UserFactory
from src.timetable.models import AttendanceRecords, EmploymentWorkType, GroupWorkerDayPermission, ShopMonthStat, TimesheetItem, WorkerDay, WorkerDayPermission
from src.timetable.tests.factories import WorkerDayFactory
from ._base import TestTimesheetMixin


@freeze_time(datetime(2021, 6, 7, 10, 10, 10))
@mock.patch.object(transaction, 'on_commit', lambda t: t())
@mock.patch('src.timetable.timesheet.tasks.calc_timesheets.apply_async')
class TestRecalcOnDataChange(TestTimesheetMixin, APITestCase):
    def setUp(self):
        self.client.force_authenticate(user=self.user_worker)

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.user_worker2 = UserFactory(email='worker2@example.com', network=cls.network)
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2)
        cls.employment_worker2 = EmploymentFactory(
            employee=cls.employee_worker2, shop=cls.shop, position=cls.position_worker,
        )
        cls.employment_work_type = EmploymentWorkType.objects.create(
            employment=cls.employment_worker2,
            work_type=cls.work_type_worker,
            priority=1,
        )
        cls.opened_vacancy = WorkerDayFactory(
            employee=None,
            employment=None,
            dt=date(2021, 6, 14),
            dttm_work_start=datetime.combine(date(2021, 6, 14), time(10)),
            dttm_work_end=datetime.combine(date(2021, 6, 14), time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            is_vacancy=True,
            shop=cls.shop,
            is_approved=True,
            cashbox_details__work_type=cls.work_type_worker,
        )
        cls.vacancy_with_worker = WorkerDayFactory(
            employee=cls.employee_worker2,
            employment=cls.employment_worker2,
            dt=date(2021, 6, 14),
            dttm_work_start=datetime.combine(date(2021, 6, 14), time(10)),
            dttm_work_end=datetime.combine(date(2021, 6, 14), time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            is_vacancy=True,
            shop=cls.shop,
            is_approved=True,
            cashbox_details__work_type=cls.work_type_worker,
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=False,
            employment=cls.employment_worker,
            employee=cls.employee_worker,
            dt=date(2021, 6, 14),
            type_id=WorkerDay.TYPE_HOLIDAY,
        )
        ShopMonthStat.objects.create(
            shop=cls.shop,
            is_approved=True,
            dttm_status_change=datetime(2021, 6, 1),
            dt=date(2021, 6, 1),
        )
        cls.add_group_perm(cls.group_worker, 'WorkerDay_approve', 'POST')
        cls.add_group_perm(cls.group_worker, 'WorkerDay_approve_vacancy', 'POST')
        cls.add_group_perm(cls.group_worker, 'WorkerDay_confirm_vacancy', 'POST')
        cls.add_group_perm(cls.group_worker, 'WorkerDay_reconfirm_vacancy_to_worker', 'POST')
        cls.add_group_perm(cls.group_worker, 'WorkerDay_refuse_vacancy', 'POST')
        cls.add_group_perm(cls.group_worker, 'WorkerDay_change_range', 'POST')
        cls.add_group_perm(cls.group_worker, 'WorkerDay_exchange_approved', 'POST')
        cls.group_worker.subordinates.add(cls.group_worker)
        GroupWorkerDayPermission.objects.bulk_create(
            GroupWorkerDayPermission(
                group=cls.group_worker,
                worker_day_permission=wdp,
            ) for wdp in WorkerDayPermission.objects.all()
        )

    def _test_recalc_called(self, call_list, employees):
        self.assertCountEqual(
            call_list,
            [
                mock.call(
                    kwargs=dict(
                        employee_id__in=[employee],
                        dt_from='2021-06-01',
                        dt_to='2021-06-30',
                    )
                )
                for employee in employees
            ],
        )

    def test_recalc_on_employment_update(self, _calc_timesheets_apply_async):
        self.employment_worker.dt_fired = date(2021, 6, 10)
        self.employment_worker.save()

        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id])
        _calc_timesheets_apply_async.reset_mock()
        with override_settings(CALC_TIMESHEET_PREV_MONTH_THRESHOLD_DAYS=20):
            self.employment_worker.dt_fired = date(2021, 6, 11)
            self.employment_worker.save()

        self.assertCountEqual(
            _calc_timesheets_apply_async.call_args_list,
            [
                mock.call(
                    kwargs=dict(
                        employee_id__in=[self.employee_worker.id],
                        dt_from='2021-05-01',
                        dt_to='2021-05-31',
                    )
                ),
                mock.call(
                    kwargs=dict(
                        employee_id__in=[self.employee_worker.id],
                        dt_from='2021-06-01',
                        dt_to='2021-06-30',
                    )
                )
            ],
        )

    def test_recalc_on_approve(self, _calc_timesheets_apply_async):
        WorkerDayFactory(
            is_approved=False,
            is_fact=False,
            shop=self.shop,
            employment=self.employment_worker,
            employee=self.employee_worker,
            dt=date(2021, 6, 12),
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime(2021, 6, 12, 11),
            dttm_work_end=datetime(2021, 6, 12, 21),
            cashbox_details__work_type=self.work_type_worker,
        )

        response = self.client.post(
            self.get_url('WorkerDay-approve'),
            data=self.dump_data(
                {
                    'dt_from': date(2021, 6, 1),
                    'dt_to': date(2021, 6, 30),
                    'shop_id': self.shop.id,
                    'is_fact': False,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id])

    def test_recalc_on_confirm_vacancy(self, _calc_timesheets_apply_async):

        response = self.client.post(
            self.get_url('WorkerDay-confirm-vacancy', pk=self.opened_vacancy.id),
            data=self.dump_data(
                {
                    'employee_id': self.employee_worker.id
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id])

    def test_recalc_on_reconfirm_vacancy(self, _calc_timesheets_apply_async):

        response = self.client.post(
            self.get_url('WorkerDay-reconfirm-vacancy-to-worker', pk=self.vacancy_with_worker.id),
            data=self.dump_data(
                {
                    'employee_id': self.employee_worker.id,
                    'user_id': self.user_worker.id,
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)

        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id, self.employee_worker2.id])

    def test_recalc_on_refuse_vacancy(self, _calc_timesheets_apply_async):

        response = self.client.post(
            self.get_url('WorkerDay-refuse-vacancy', pk=self.vacancy_with_worker.id),
        )
        self.assertEqual(response.status_code, 200)

        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker2.id])

    def test_recalc_on_change_range(self, _calc_timesheets_apply_async):
        data = {
            'dt_from': date(2021, 6, 3),
            'dt_to': date(2021, 6, 10),
            'is_approved': True,
            'worker': self.employee_worker.tabel_code,
            'type': WorkerDay.TYPE_VACATION,
        }
        
        response = self.client.post(
            self.get_url('WorkerDay-change-range'),
            data=self.dump_data(
                {
                    'ranges': [data]
                }
            ),
            content_type='application/json',
        )
        self.assertEqual(response.status_code, 200)
        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id])

        _calc_timesheets_apply_async.reset_mock()
        data['is_approved'] = False
        data['dt_to'] = date(2021, 6, 15)
        response = self.client.post(
            self.get_url('WorkerDay-change-range'),
            data=self.dump_data(
                {
                    'ranges': [data]
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        _calc_timesheets_apply_async.assert_not_called()

    def test_recalc_on_exchange_approved(self, _calc_timesheets_apply_async):

        response = self.client.post(
            self.get_url('WorkerDay-exchange-approved'),
            data=self.dump_data(
                {
                    'employee1_id': self.employee_worker.id,
                    'employee2_id': self.employee_worker2.id,
                    'dates': [date(2021, 6, 14),]
                }
            ),
            content_type='application/json',
        )

        self.assertEqual(response.status_code, 200)
        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id, self.employee_worker2.id])

    def test_recalc_on_attendance_records(self, _calc_timesheets_apply_async):
        WorkerDay.objects.all().delete()

        AttendanceRecords.objects.create(
            dt=date(2021, 6, 14),
            dttm=datetime(2021, 6, 14, 10, 5),
            employee=self.employee_worker,
            user=self.user_worker,
            shop=self.shop,
            type=AttendanceRecords.TYPE_COMING,
        )

        _calc_timesheets_apply_async.assert_not_called()

        AttendanceRecords.objects.create(
            dt=date(2021, 6, 14),
            dttm=datetime(2021, 6, 14, 20, 13),
            employee=self.employee_worker,
            user=self.user_worker,
            shop=self.shop,
            type=AttendanceRecords.TYPE_LEAVING,
        )

        self._test_recalc_called(_calc_timesheets_apply_async.call_args_list, [self.employee_worker.id])
