from datetime import timedelta, time, date, datetime

from django.utils import timezone
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APITestCase

from src.apps.base.models import Employment, Employee, WorkerPosition
from src.apps.timetable.models import WorkerDay, WorkTypeName, WorkType
from src.common.mixins.tests import TestsHelperMixin
from src.common.models_converter import Converter


class TestWorkShiftViewSet(TestsHelperMixin, APITestCase):
    maxDiff = None

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.work_type1 = WorkType.objects.create(shop=cls.shop2, work_type_name=cls.work_type_name1)
        cls.today = timezone.now().today()
        cls.dt_str = cls.today.strftime('%Y-%m-%d')

    def setUp(self):
        self._set_authorization_token(self.user2.username)

    def _test_work_shift(self, dt, username, expected_start=None, expected_end=None, expected_shop_code=None):
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-work-shift'),
            data={'dt': dt, 'worker': username},
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        exp_resp = {
            "dt": dt,
            "worker": username,
            "dttm_work_start": (expected_start - timedelta(
                hours=self.shop2.get_tz_offset())).isoformat() if expected_start else None,
            "dttm_work_end": (expected_end - timedelta(
                hours=self.shop2.get_tz_offset())).isoformat() if expected_end else None
        }
        if expected_shop_code:
            exp_resp['shop'] = expected_shop_code
        self.assertDictEqual(resp.json(), exp_resp)

    def test_work_shift(self):
        self._test_work_shift(self.dt_str, self.user2.username, None, None)

        dttm_start = datetime.combine(self.today, time(10))
        wd = WorkerDay.objects.create(
            dttm_work_start=dttm_start,
            dttm_work_end=None,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=True,
            dt=self.dt_str,
            shop=self.work_type1.shop,
            employee=self.employee2,
            employment=self.employment2,
        )
        self._test_work_shift(self.dt_str, self.user2.username, dttm_start, None, self.shop2.code)

        dttm_end = datetime.combine(self.today, time(20))
        wd.dttm_work_end = dttm_end
        wd.save()
        self._test_work_shift(self.dt_str, self.user2.username, dttm_start, dttm_end, self.shop2.code)

    def test_work_shift_with_type_empty_excluded(self):
        self._test_work_shift(self.dt_str, self.user2.username, None, None)

        WorkerDay.objects.create(
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            type_id=WorkerDay.TYPE_EMPTY,
            is_fact=True,
            is_approved=True,
            dt=self.dt_str,
            shop=self.work_type1.shop,
            employee=self.employee2,
            employment=self.employment2,
        )
        self._test_work_shift(self.dt_str, self.user2.username, None, None)

    def test_work_shift_with_empty_shop_excluded(self):
        self._test_work_shift(self.dt_str, self.user2.username, None, None)

        WorkerDay.objects.create(
            dttm_work_start=datetime.combine(self.today, time(10)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=True,
            dt=self.dt_str,
            shop=None,
            employee=self.employee2,
            employment=self.employment2,
        )
        self._test_work_shift(self.dt_str, self.user2.username, None, None)

    def test_cant_get_work_shift_for_someones_user(self):
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-work-shift'),
            data={'dt': self.dt_str, 'worker': self.user3.username},
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_no_active_employee(self):
        self._authorize_tick_point()
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
        )
        self.assertEqual(len(resp.json()), 5)
        dt_hired = (datetime.now() + timedelta(hours=self.shop.get_tz_offset())).date() + timedelta(1)
        Employment.objects.all().update(dt_hired=dt_hired, dt_fired=None)
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
        )
        self.assertEqual(len(resp.json()), 0)

    def test_get_worker_days(self):
        self._authorize_tick_point()
        self.employee2.tabel_code = '1235'
        self.employee2.save()
        position = WorkerPosition.objects.create(
            name='Работник',
            network=self.network,
        )
        self.second_employee = Employee.objects.create(
            tabel_code='1234', 
            user=self.user2,
        )
        emp = Employment.objects.create(
            employee=self.second_employee,
            shop=self.shop,
            position=position,
        )
        wd1 = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today,
            dttm_work_start=datetime.combine(self.today, time(8)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            shop=self.shop,
            is_approved=True,
        )
        wd2 = WorkerDay.objects.create(
            employee=self.second_employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today,
            dttm_work_start=datetime.combine(self.today, time(15)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            shop=self.shop,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.second_employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today - timedelta(1),
            dttm_work_start=datetime.combine(self.today - timedelta(1), time(8)),
            dttm_work_end=datetime.combine(self.today - timedelta(1), time(14)),
            shop=self.shop,
            is_approved=True,
        )
        with freeze_time(datetime.now() - timedelta(hours=self.shop.get_tz_offset())):
            resp = self.client.get(
                self.get_url('TimeAttendanceWorkerDay-list'),
            )
        user2 = list(filter(lambda x: x['user_id'] == self.user2.id, resp.json()))[0]
        user2['employees'] = sorted(user2['employees'], key=lambda i: i['id'])
        user2_data = {
            'user_id': self.user2.id, 
            'employees': [
                {
                    'id': self.employee2.id,
                    'shop': {
                        'id': self.employment2.shop.id, 
                        'name': self.employment2.shop.name,
                        'timezone': 'Europe/Moscow',
                    },
                    'tabel_code': self.employee2.tabel_code, 
                    'worker_days': [
                        {
                            'id': wd1.id, 
                            'dttm_work_start': Converter.convert_datetime(wd1.dttm_work_start),
                            'dttm_work_end': Converter.convert_datetime(wd1.dttm_work_end),
                        }
                    ],
                    'position': ''
                }, 
                {
                    'id': self.second_employee.id,
                    'tabel_code': self.second_employee.tabel_code, 
                    'shop': {
                        'id': emp.shop.id, 
                        'name': emp.shop.name,
                        'timezone': 'Europe/Moscow',
                    },
                    'worker_days': [
                        {
                            'id': wd2.id, 
                            'dttm_work_start': Converter.convert_datetime(wd2.dttm_work_start),
                            'dttm_work_end': Converter.convert_datetime(wd2.dttm_work_end),
                        }
                    ],
                    'position': 'Работник'
                }
            ], 
            'first_name': 'Иван2', 
            'last_name': 'Иванов', 
            'avatar': None,
            'network': {
                'allowed_geo_distance_km': None,
                'allow_creation_several_wdays_for_one_employee_for_one_date': False,
                'allow_to_manually_set_is_vacancy': False,
                'allowed_interval_for_early_departure': '00:00:00',
                'allowed_interval_for_late_arrival': '00:00:00',
                'biometry_in_tick_report': False,
                'default_stats': {
                    'day_bottom': 'deadtime',
                    'day_top': 'covering',
                    'employee_bottom': 'norm_hours_curr_month',
                    'employee_top': 'work_hours_total',
                    'timesheet_employee_bottom': 'sawh_hours',
                    'timesheet_employee_top': 'fact_total_all_hours_sum',
                },
                'enable_camera_ticks': False,
                'id': self.user2.network_id,
                'logo': None,
                'name': 'По умолчанию',
                'primary_color': '',
                'secondary_color': '',
                'show_tabel_graph': True,
                'show_worker_day_additional_info': False,
                'show_restrict_editing_shifts_button': False,
                'show_worker_day_tasks': False,
                'show_user_biometrics_block': False,
                'use_internal_exchange': True,
                'show_checkbox_for_inspection_version': True,
                'unaccounted_overtime_threshold': 60,
                'forbid_edit_employments_came_through_integration': True,
                'forbid_edit_work_days_came_through_integration': False,
                'get_position_from_work_type_name_in_calc_timesheet': False,
                'trust_tick_request': False,
                'show_cost_for_inner_vacancies': False,
                'rebuild_timetable_min_delta': 2,
                'show_remaking_choice': False,
                'analytics_iframe': '',
                'analytics_type': 'metabase',
                'show_employee_shift_schedule_tab': False,
                'display_chart_in_other_stores': False,
                'url': None,
                'shop_name_form': {
                    "singular": {
                        "I": "магазин",
                        "R": "магазина",
                        "D": "магазину",
                        "V": "магазин",
                        "T": "магазином",
                        "P": "магазине"
                    },
                    "plural": {
                        "I": "магазины",
                        "R": "магазинов",
                        "D": "магазинам",
                        "V": "магазины",
                        "T": "магазинами",
                        "P": "магазинах"
                    }
                }
            },
        }
        self.assertEqual(len(resp.json()), 5)
        self.assertEqual(user2, user2_data)

    def test_get_worker_days_night_shift(self):
        self._authorize_tick_point()
        self.employee2.tabel_code = '1235'
        self.employee2.save()
        self.shop.timezone = 'UTC'
        self.shop.save()
        position = WorkerPosition.objects.create(
            name='Работник',
            network=self.network,
        )
        self.second_employee = Employee.objects.create(
            tabel_code='1234', 
            user=self.user2,
        )
        emp = Employment.objects.create(
            employee=self.second_employee,
            shop=self.shop,
            position=position,
        )
        wd1 = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today - timedelta(1),
            dttm_work_start=datetime.combine(self.today - timedelta(1), time(22)),
            dttm_work_end=datetime.combine(self.today, time(8)),
            shop=self.shop,
            is_approved=True,
        )
        wd2 = WorkerDay.objects.create(
            employee=self.second_employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today,
            dttm_work_start=datetime.combine(self.today, time(15)),
            dttm_work_end=datetime.combine(self.today, time(20)),
            shop=self.shop,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.second_employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today - timedelta(1),
            dttm_work_start=datetime.combine(self.today - timedelta(1), time(8)),
            dttm_work_end=datetime.combine(self.today - timedelta(1), time(14)),
            shop=self.shop,
            is_approved=True,
        )
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
        )
        user2 = list(filter(lambda x: x['user_id'] == self.user2.id, resp.json()))[0]
        user2['employees'] = sorted(user2['employees'], key=lambda i: i['id'])
        user2_data = {
            'user_id': self.user2.id, 
            'employees': [
                {
                    'id': self.employee2.id,
                    'shop': {
                        'id': self.employment2.shop.id, 
                        'name': self.employment2.shop.name,
                        'timezone': 'UTC',
                    },
                    'tabel_code': self.employee2.tabel_code, 
                    'worker_days': [
                        {
                            'id': wd1.id, 
                            'dttm_work_start': Converter.convert_datetime(wd1.dttm_work_start),
                            'dttm_work_end': Converter.convert_datetime(wd1.dttm_work_end),
                        }
                    ],
                    'position': ''
                }, 
                {
                    'id': self.second_employee.id,
                    'shop': {
                        'id': emp.shop.id, 
                        'name': emp.shop.name,
                        'timezone': 'UTC',
                    },
                    'tabel_code': self.second_employee.tabel_code, 
                    'worker_days': [
                        {
                            'id': wd2.id, 
                            'dttm_work_start': Converter.convert_datetime(wd2.dttm_work_start),
                            'dttm_work_end': Converter.convert_datetime(wd2.dttm_work_end),
                        }
                    ],
                    'position': 'Работник'
                }
            ], 
            'first_name': 'Иван2', 
            'last_name': 'Иванов', 
            'avatar': None,
            'network': {
                'allowed_geo_distance_km': None,
                'allow_creation_several_wdays_for_one_employee_for_one_date': False,
                'allow_to_manually_set_is_vacancy': False,
                'allowed_interval_for_early_departure': '00:00:00',
                'allowed_interval_for_late_arrival': '00:00:00',
                'biometry_in_tick_report': False,
                'default_stats': {
                    'day_bottom': 'deadtime',
                    'day_top': 'covering',
                    'employee_bottom': 'norm_hours_curr_month',
                    'employee_top': 'work_hours_total',
                    'timesheet_employee_bottom': 'sawh_hours',
                    'timesheet_employee_top': 'fact_total_all_hours_sum',
                },
                'enable_camera_ticks': False,
                'id': self.user2.network_id,
                'logo': None,
                'name': 'По умолчанию',
                'primary_color': '',
                'secondary_color': '',
                'show_tabel_graph': True,
                'show_worker_day_additional_info': False,
                'show_restrict_editing_shifts_button': False,
                'show_worker_day_tasks': False,
                'show_user_biometrics_block': False,
                'use_internal_exchange': True,
                'show_checkbox_for_inspection_version': True,
                'unaccounted_overtime_threshold': 60,
                'forbid_edit_employments_came_through_integration': True,
                'forbid_edit_work_days_came_through_integration': False,
                'get_position_from_work_type_name_in_calc_timesheet': False,
                'trust_tick_request': False,
                'show_cost_for_inner_vacancies': False,
                'rebuild_timetable_min_delta': 2,
                'show_remaking_choice': False,
                'analytics_iframe': '',
                'analytics_type': 'metabase',
                'show_employee_shift_schedule_tab': False,
                'display_chart_in_other_stores': False,
                'url': None,
                'shop_name_form': {
                    "singular": {
                        "I": "магазин",
                        "R": "магазина",
                        "D": "магазину",
                        "V": "магазин",
                        "T": "магазином",
                        "P": "магазине"
                    },
                    "plural": {
                        "I": "магазины",
                        "R": "магазинов",
                        "D": "магазинам",
                        "V": "магазины",
                        "T": "магазинами",
                        "P": "магазинах"
                    }
                }
            },
        }
        self.assertEqual(len(resp.json()), 5)
        self.assertEqual(user2, user2_data)

    def test_auth_get_tz(self):
        response = self._authorize_tick_point()
        self.assertEqual(response.json()['shop']['timezone'], 'Europe/Moscow')

    def test_get_worker_days_night_shift_tz(self):
        self._authorize_tick_point()
        self.employee2.tabel_code = '1235'
        self.employee2.save()
        self.shop.timezone = 'Asia/Vladivostok'
        self.shop.save()
        if datetime.now().hour <= 13:
            self.today -= timedelta(1)
        position = WorkerPosition.objects.create(
            name='Работник',
            network=self.network,
        )
        self.second_employee = Employee.objects.create(
            tabel_code='1234', 
            user=self.user2,
        )
        emp = Employment.objects.create(
            employee=self.second_employee,
            shop=self.shop,
            position=position,
        )
        wd1 = WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today,
            dttm_work_start=datetime.combine(self.today, time(22)),
            dttm_work_end=datetime.combine(self.today + timedelta(1), time(8)),
            shop=self.shop,
            is_approved=True,
        )
        wd2 = WorkerDay.objects.create(
            employee=self.second_employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today + timedelta(1),
            dttm_work_start=datetime.combine(self.today + timedelta(1), time(15)),
            dttm_work_end=datetime.combine(self.today + timedelta(1), time(20)),
            shop=self.shop,
            is_approved=True,
        )
        WorkerDay.objects.create(
            employee=self.second_employee,
            employment=emp,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=self.today,
            dttm_work_start=datetime.combine(self.today, time(8)),
            dttm_work_end=datetime.combine(self.today, time(14)),
            shop=self.shop,
            is_approved=True,
        )
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
        )
        user2 = list(filter(lambda x: x['user_id'] == self.user2.id, resp.json()))[0]
        user2['employees'] = sorted(user2['employees'], key=lambda i: i['id'])
        user2_data = {
            'user_id': self.user2.id, 
            'employees': [
                {
                    'id': self.employee2.id,
                    'shop': {
                        'id': self.employment2.shop.id, 
                        'name': self.employment2.shop.name,
                        'timezone': 'Asia/Vladivostok',
                    },
                    'tabel_code': self.employee2.tabel_code, 
                    'worker_days': [
                        {
                            'id': wd1.id, 
                            'dttm_work_start': Converter.convert_datetime(wd1.dttm_work_start),
                            'dttm_work_end': Converter.convert_datetime(wd1.dttm_work_end),
                        }
                    ],
                    'position': ''
                }, 
                {
                    'id': self.second_employee.id,
                    'shop': {
                        'id': emp.shop.id, 
                        'name': emp.shop.name,
                        'timezone': 'Asia/Vladivostok',
                    },
                    'tabel_code': self.second_employee.tabel_code, 
                    'worker_days': [
                        {
                            'id': wd2.id, 
                            'dttm_work_start': Converter.convert_datetime(wd2.dttm_work_start),
                            'dttm_work_end': Converter.convert_datetime(wd2.dttm_work_end),
                        }
                    ],
                    'position': 'Работник'
                }
            ], 
            'first_name': 'Иван2', 
            'last_name': 'Иванов', 
            'avatar': None,
            'network': {
                'allowed_geo_distance_km': None,
                'allow_creation_several_wdays_for_one_employee_for_one_date': False,
                'allow_to_manually_set_is_vacancy': False,
                'allowed_interval_for_early_departure': '00:00:00',
                'allowed_interval_for_late_arrival': '00:00:00',
                'biometry_in_tick_report': False,
                'default_stats': {
                    'day_bottom': 'deadtime',
                    'day_top': 'covering',
                    'employee_bottom': 'norm_hours_curr_month',
                    'employee_top': 'work_hours_total',
                    'timesheet_employee_bottom': 'sawh_hours',
                    'timesheet_employee_top': 'fact_total_all_hours_sum',
                },
                'enable_camera_ticks': False,
                'id': self.user2.network_id,
                'logo': None,
                'name': 'По умолчанию',
                'primary_color': '',
                'secondary_color': '',
                'show_tabel_graph': True,
                'show_worker_day_additional_info': False,
                'show_restrict_editing_shifts_button': False,
                'show_worker_day_tasks': False,
                'show_user_biometrics_block': False,
                'use_internal_exchange': True,
                'show_checkbox_for_inspection_version': True,
                'unaccounted_overtime_threshold': 60,
                'forbid_edit_employments_came_through_integration': True,
                'forbid_edit_work_days_came_through_integration': False,
                'get_position_from_work_type_name_in_calc_timesheet': False,
                'trust_tick_request': False,
                'show_cost_for_inner_vacancies': False,
                'rebuild_timetable_min_delta': 2,
                'show_remaking_choice': False,
                'analytics_iframe': '',
                'analytics_type': 'metabase',
                'show_employee_shift_schedule_tab': False,
                'display_chart_in_other_stores': False,
                'url': None,
                'shop_name_form': {
                    "singular": {
                        "I": "магазин",
                        "R": "магазина",
                        "D": "магазину",
                        "V": "магазин",
                        "T": "магазином",
                        "P": "магазине"
                    },
                    "plural": {
                        "I": "магазины",
                        "R": "магазинов",
                        "D": "магазинам",
                        "V": "магазины",
                        "T": "магазинами",
                        "P": "магазинах"
                    }
                }
            },
        }
        self.assertEqual(len(resp.json()), 5)
        self.assertEqual(user2, user2_data)
