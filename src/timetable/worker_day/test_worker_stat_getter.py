from datetime import date, timedelta, datetime, time
from unittest import expectedFailure, mock

from dateutil.relativedelta import relativedelta
from django.core.cache import cache
from django.db import transaction
from django.test import override_settings

from rest_framework.test import APITestCase

from etc.scripts import fill_calendar
from src.base.models import ProductionDay, Region
from src.base.tests.factories import (
    GroupFactory,
    NetworkFactory,
    ShopFactory,
    UserFactory,
    EmploymentFactory,
    ShopSettingsFactory,
    WorkerPositionFactory,
    EmployeeFactory,
)
from src.celery.tasks import set_prod_cal_cache_cur_and_next_month
from src.timetable.models import GroupWorkerDayPermission, WorkerDay, WorkerDayPermission, WorkerDayType
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin
from .stat import WorkersStatsGetter


class TestWorkersStatsGetter(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_from = date(2020, 12, 1)
        cls.dt_to = date(2020, 12, 31)
        cls.network = NetworkFactory(crop_work_hours_by_shop_schedule=False)
        cls.shop_settings = ShopSettingsFactory(
            breaks__value='[[0, 2040, [60]]]')
        cls.shop = ShopFactory(settings=cls.shop_settings)
        cls.shop2 = ShopFactory(settings=cls.shop_settings)
        cls.user = UserFactory()
        cls.employee = EmployeeFactory(user=cls.user)
        cls.group = GroupFactory()
        cls.position = WorkerPositionFactory(group=cls.group)
        cls.employment = EmploymentFactory(
            shop=cls.shop, employee=cls.employee,
            dt_hired=cls.dt_from - timedelta(days=90), dt_fired=None,
            position=cls.position,
        )
        fill_calendar.fill_days('2020.12.1', '2020.12.31', cls.shop.region.id)

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.network.refresh_from_db()
        self.position.refresh_from_db()
        cache.clear()

    def _set_accounting_period_length(self, length):
        self.network.accounting_period_length = length
        self.network.save(update_fields=('accounting_period_length',))

    def _get_worker_stats(self, dt_from=None, dt_to=None):
        return WorkersStatsGetter(
            dt_from=dt_from or self.dt_from,
            dt_to=dt_to or self.dt_to,
            shop_id=self.shop.id,
        ).run()

    def test_work_days_count(self):
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')

        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 4), type_id='H')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 5), type_id='H')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 6), type_id='S')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 7), type_id='S')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 8), type_id='S')
        stats = self._get_worker_stats()

        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['work_days'],
            {
                'total': 3,
                'selected_shop': 2,
                'other_shops': 1,
            }
        )

        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_days'],
            {
                'total': 2,
                'selected_shop': 2,
                'other_shops': 0,
            }
        )

    def test_work_hours(self):
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type_id='W')
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours'],
            {
                'acc_period': 27.0,
                'other_shops': 9.0,
                'selected_shop': 18.0,
                'total': 27.0,
                'until_acc_period_end': 27.0
            }
        )

    def test_day_type(self):
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 3), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 4), type_id='H')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop2, dt=date(2020, 12, 5), type_id='S')
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['day_type'],
            {
                'W': 3,
                'H': 1,
                'S': 1,
            }
        )

    def test_norm_hours_curr_month(self):
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['norm_hours']['curr_month'],
            183.0,
        )

    def test_overtime_curr_month(self):
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 2), type_id='W')
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['overtime']['curr_month'],
            -165.0,
        )

    def test_work_hours_for_prev_months_counted_from_fact(self):
        self._set_accounting_period_length(3)
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 10, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 11, 1), type_id='W')
        WorkerDayFactory(is_fact=True, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')

        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 10, 1), type_id='W')
        WorkerDayFactory(is_fact=False, is_approved=True, employee=self.employee, employment=self.employment,
                         shop=self.shop, dt=date(2020, 12, 1), type_id='W')

        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours']['prev_months'],
            18.0
        )
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['work_hours']['prev_months'],
            18.0
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours']['acc_period'],
            27.0
        )
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['work_hours']['acc_period'],
            27.0
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['overtime']['acc_period'],
            -491.0
        )
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['overtime']['acc_period'],
            -491.0
        )

    def test_hours_in_a_week_affect_norm_hours(self):
        self.position.hours_in_a_week = 39
        self.position.save()

        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['plan']['approved']['norm_hours']['curr_month'],
            178.40000000000003,
        )

    def test_get_hours_sum_and_days_count_by_type(self):
        new_wd_type = self._create_san_day()
        dt = date(2021, 6, 1)
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=self.dt_from,
            type_id=new_wd_type.code,
            dttm_work_start=datetime.combine(self.dt_from, time(10)),
            dttm_work_end=datetime.combine(self.dt_from, time(20)),
        )
        stats = self._get_worker_stats()
        self.assertIn('hours_by_type', stats[self.employee.id]['fact']['approved'])
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['hours_by_type']['SD'],
            9.0,
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['day_type']['SD'],
            1,
        )

    def test_days_count_by_type_for_multiple_wdays_on_one_date(self):
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=self.dt_from,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_from, time(10)),
            dttm_work_end=datetime.combine(self.dt_from, time(14)),
        )
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=self.dt_from,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_from, time(17)),
            dttm_work_end=datetime.combine(self.dt_from, time(22)),
        )
        stats = self._get_worker_stats()
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['day_type'][WorkerDay.TYPE_WORKDAY],
            1,
        )

    def test_wd_types_with_is_work_hours_false_not_counted_in_work_hours_sum(self):
        """
        Проверка, что типы дней с is_work_hours=False не учитываются в сумме "Рабочих часов"
        """
        san_day = self._create_san_day()
        dt_now = date.today()
        WorkerDayFactory(
            is_approved=True,
            is_fact=True,
            shop=self.shop,
            employment=self.employment,
            employee=self.employee,
            dt=dt_now,
            type=san_day,
            dttm_work_start=datetime.combine(dt_now, time(10)),
            dttm_work_end=datetime.combine(dt_now, time(20)),
        )
        stats = self._get_worker_stats(dt_from=dt_now, dt_to=dt_now)
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['work_hours']['total'],
            0,
        )
        self.assertEqual(
            stats[self.employee.id]['fact']['approved']['overtime']['curr_month'],
            0,
        )

    def _test_cache(self, call_count, called_with=[], resp_count=2, dt_from=None, dt_to=None):

        def _data_for_employee(e):
            return [
                {
                    'employee_id': e,
                    'employment_id': self.employments[e],
                    'dt__month': self.dt_from.month,
                    'period_start': self.dt_from,
                    'period_end': self.dt_to,
                    'has_vacation_or_sick_plan_approved': False,
                    'vacation_or_sick_plan_approved_count': 0,
                    'vacation_or_sick_plan_approved_count_selected_period': 0,
                    'has_vacation_or_sick_plan_not_approved': False,
                    'vacation_or_sick_plan_not_approved_count': 0,
                    'vacation_or_sick_plan_not_approved_count_selected_period': 0,
                    'norm_hours_acc_period': 156,
                    'norm_hours_prev_months': 156,
                    'norm_hours_curr_month': 156,
                    'norm_hours_curr_month_end': 156,
                    'norm_hours_selected_period': 156,
                    'empl_days_count': 20,
                    'empl_days_count_selected_period': 20,
                    'empl_days_count_outside_of_selected_period': 20,
                    'dts': [],
                }
            ]
        
        mock_prod_call = mock.MagicMock(side_effect=_data_for_employee)

        with mock.patch.object(WorkersStatsGetter, '_get_prod_cal_for_employee', mock_prod_call):
            stat = self._get_worker_stats(dt_from=dt_from, dt_to=dt_to)
            self.assertEqual(len(stat), resp_count)
            self.assertEqual(mock_prod_call.call_count, call_count)
            if called_with:
                calls = [mock.call(call) for call in called_with]
                mock_prod_call.assert_has_calls(calls, any_order=True)

    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_cache(self):
        self.user2 = UserFactory()
        self.employee2 = EmployeeFactory(user=self.user2)
        self.employment2 = EmploymentFactory(
            shop=self.shop, employee=self.employee2,
            dt_hired=self.dt_from - timedelta(days=90), dt_fired=None,
            position=self.position,
        )
        self.employments = {
            employment.employee_id: employment.id
            for employment in [self.employment, self.employment2]
        }
        position2 = WorkerPositionFactory(name='Вторая должность')
        
        self._test_cache(2, [self.employee.id, self.employee2.id])
        self._test_cache(0)

        self.position.hours_in_a_week = 39
        self.position.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        self.position.ordering = 2
        self.position.save()
        self._test_cache(0)

        p_day, _ = ProductionDay.objects.update_or_create(dt=self.dt_from, region=self.shop.region, defaults={'type': ProductionDay.TYPE_WORK})
        self._test_cache(2, [self.employee.id, self.employee2.id])

        p_day.type = ProductionDay.TYPE_HOLIDAY
        p_day.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        w_type = WorkerDayType.objects.get(code=WorkerDay.TYPE_VACATION)
        w_type.is_reduce_norm = False
        w_type.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        w_type.is_dayoff = False
        w_type.save()
        self._test_cache(0)
        
        self.network.accounting_period_length = 12
        self.network.save()
        self._test_cache(2, [self.employee.id, self.employee2.id])

        with mock.patch.object(transaction, 'on_commit', lambda t: t()):
            region2 = Region.objects.create(name='Татарстан')
            self.shop.region = region2
            self.shop.save()
            self._test_cache(2, [self.employee.id, self.employee2.id])

            self.employment2.norm_work_hours = 90
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            self.employment2.dt_hired = self.dt_from - timedelta(days=95)
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            self.employment2.dt_fired = self.dt_to + timedelta(days=60)
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            self.employment2.position = position2
            self.employment2.save()
            self._test_cache(1, [self.employee2.id])

            w_type.is_reduce_norm = True
            w_type.is_dayoff = True
            w_type.save()
            self._test_cache(2, [self.employee.id, self.employee2.id])

            wd = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type=w_type,
                dt=self.dt_from,
                dttm_work_start=None,
                dttm_work_end=None,
            )
            self._test_cache(1, [self.employee2.id])

            wd.save()
            self._test_cache(1, [self.employee2.id])

            wd.delete()
            self._test_cache(1, [self.employee2.id])

            wd2 = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type_id=WorkerDay.TYPE_HOLIDAY,
                dt=self.dt_from + timedelta(1),
                dttm_work_start=None,
                dttm_work_end=None,
            )
            self._test_cache(0)

            wd2.save()
            self._test_cache(0)

            wd2.delete()
            self._test_cache(0)

            wd = WorkerDayFactory(
                employee=self.employee2,
                employment=self.employment2,
                type_id=WorkerDay.TYPE_HOLIDAY,
                dt=self.dt_from,
                dttm_work_start=None,
                dttm_work_end=None,
                is_fact=False,
                is_approved=False,
            )
            GroupWorkerDayPermission.objects.bulk_create(
                GroupWorkerDayPermission(
                    group=self.group,
                    worker_day_permission=wdp,
                    employee_type=GroupWorkerDayPermission.MY_NETWORK_EMPLOYEE,
                    shop_type=GroupWorkerDayPermission.MY_NETWORK_SHOPS,
                ) for wdp in WorkerDayPermission.objects.all()
            )
            self.add_group_perm(self.group, 'WorkerDay_approve', 'POST')
            self.add_group_perm(self.group, 'WorkerDay_delete_worker_days', 'POST')
            self.create_departments_and_users
            response = self.client.post(
                self.get_url('WorkerDay-approve'), 
                {
                    'dt_from': self.dt_from, 
                    'dt_to': self.dt_to, 
                    'shop_id': self.shop.id,
                    'is_fact': False,
                },
            )
            self.assertEqual(response.status_code, 200)

            self._test_cache(1, [self.employee2.id])

            wd2 = WorkerDayFactory(
                employee=self.employee,
                employment=self.employment,
                type_id=WorkerDay.TYPE_VACATION,
                dt=self.dt_from,
                dttm_work_start=None,
                dttm_work_end=None,
            )
            self._test_cache(1, [self.employee.id])

            response = self.client.post(
                self.get_url('WorkerDay-delete-worker-days'), 
                {
                    'dates': [self.dt_from,], 
                    'employee_ids': [self.employee.id, self.employee2.id],
                    'is_fact': False,
                },
            )
            self.assertEqual(response.status_code, 200)
            self._test_cache(1, [self.employee.id])

            batch_data = [
                {
                    'dt': self.dt_from + timedelta(2),
                    'employee_id': self.employee2.id,
                    'employment_id': self.employment2.id,
                    'type_id': WorkerDay.TYPE_VACATION,
                    'is_fact': False,
                    'is_approved': False,
                },
                {
                    'dt': self.dt_from + timedelta(3),
                    'employee_id': self.employee2.id,
                    'employment_id': self.employment2.id,
                    'type_id': WorkerDay.TYPE_HOLIDAY,
                    'is_fact': False,
                    'is_approved': False,
                }
            ]

            created_days, result = WorkerDay.batch_update_or_create(batch_data)
            for i, data in enumerate(batch_data):
                data['id'] = created_days[i].id
            self._test_cache(1, [self.employee2.id])
            self.assertEqual(result.get('WorkerDay', {}).get('created'), 2)
            
            batch_data[0]['type_id'] = WorkerDay.TYPE_HOLIDAY
            _, result = WorkerDay.batch_update_or_create(batch_data)
            self.assertEqual(result.get('WorkerDay', {}).get('updated'), 1)
            self._test_cache(1, [self.employee2.id])

            batch_data[0]['type_id'] = WorkerDay.TYPE_EMPTY
            _, result = WorkerDay.batch_update_or_create(batch_data)
            self.assertEqual(result.get('WorkerDay', {}).get('updated'), 1)
            self._test_cache(0)

            batch_data[1]['type_id'] = WorkerDay.TYPE_VACATION
            _, result = WorkerDay.batch_update_or_create(batch_data)
            self.assertEqual(result.get('WorkerDay', {}).get('updated'), 1)
            self._test_cache(1, [self.employee2.id])

            _, result = WorkerDay.batch_update_or_create(
                data=[],
                delete_scope_fields_list=['dt', 'is_approved', 'is_fact', 'employee_id'],
                delete_scope_values_list=batch_data,
            )
            self.assertEqual(result.get('WorkerDay', {}).get('deleted'), 2)
            self._test_cache(1, [self.employee2.id])

            batch_data = [
                {
                    'dt': self.dt_from + timedelta(2),
                    'employee_id': self.employee.id,
                    'employment_id': self.employment.id,
                    'type_id': WorkerDay.TYPE_HOLIDAY,
                    'is_fact': False,
                    'is_approved': False,
                },
            ]
            _, result = WorkerDay.batch_update_or_create(batch_data)
            self.assertEqual(result.get('WorkerDay', {}).get('created'), 1)
            self._test_cache(0)

            cache.clear()
            self.employment2.dt_fired = None
            self.employment2.save()

            dt_from_cur, dt_to_cur = date.today().replace(day=1), date.today() + relativedelta(day=31)
            dt_from_next = (dt_from_cur + relativedelta(months=1)).replace(day=1)
            dt_to_next = dt_from_next + relativedelta(day=31)
            fill_calendar.fill_days(dt_from_cur.strftime('%Y.%m.%d'), dt_to_next.strftime('%Y.%m.%d'), self.shop.region.id)
            set_prod_cal_cache_cur_and_next_month()
            self._test_cache(0, dt_from=dt_from_cur, dt_to=dt_to_cur)
            self._test_cache(0, dt_from=dt_from_next, dt_to=dt_to_next)

            self._test_cache(2, [self.employee.id, self.employee2.id])
            self.employment2.delete()
            self._test_cache(0, resp_count=1)
            self.assertIsNone(cache.get(f'prod_cal_{self.dt_from}_{self.dt_to}_{self.employee2.id}'))

    def test_get_worker_stat_with_empty_employee_id__in(self):
        self.add_group_perm(
            self.group,
            'WorkerDay_worker_stat',
            'GET',
        )
        response = self.client.get(
            f'/rest_api/worker_day/worker_stat/?shop_id={self.shop.id}&dt_from={self.dt_from}&dt_to={self.dt_to}&employee_id__in=',
        )
        self.assertEqual(response.status_code, 200)
