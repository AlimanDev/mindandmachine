from decimal import Decimal

from rest_framework.test import APITestCase

from src.base.models import (
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleInterval,
)
from src.base.tests.factories import (
    NetworkFactory,
    ShopFactory,
    UserFactory,
    EmploymentFactory,
    GroupFactory,
    EmployeeFactory,
)
from src.util.mixins.tests import TestsHelperMixin


class TestShiftScheduleViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.user = UserFactory(network=cls.network)
        cls.shop = ShopFactory(
            network=cls.network,
            tm_open_dict='{"0": "08:00:00","1": "08:00:00","2": "08:00:00","3": "08:00:00","4": "08:00:00"}',
            tm_close_dict='{"0": "20:00:00","1": "20:00:00","2": "20:00:00","3": "20:00:00","4": "19:00:00"}',
        )
        cls.group = GroupFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user, tabel_code='empl')
        cls.employment = EmploymentFactory(
            employee=cls.employee, shop=cls.shop, function_group=cls.group)
        cls.add_group_perm(cls.group, 'ShiftSchedule_batch_update_or_create', 'POST')
        cls.add_group_perm(cls.group, 'Employee_shift_schedule', 'GET')

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.shop.refresh_from_db()

    def test_can_create_employee_shift_schedule(self):
        shift_schedules_data_2021 = [
            {
                "code": "1",
                "name": "График 1",
                "employee__tabel_code": self.employee.tabel_code,
                "days": [
                    {
                        "code": "1_2021-01-01",
                        "dt": "2021-01-01",
                        "day_type": 'W',
                        "work_hours": Decimal("13.00"),
                    },
                    {
                        "code": "1_2021-01-02",
                        "dt": "2021-01-02",
                        "day_type": 'H',
                        "work_hours": Decimal("0.00"),
                    },
                    {
                        "code": "1_2021-01-07",
                        "dt": "2021-01-07",
                        "day_type": 'W',
                        "work_hours": Decimal("12.00"),
                    },
                ]
            }
        ]
        options = {
            "by_code": True,
            "return_response": True,
            "delete_scope_fields_list": ["code"],
        }
        data = {
            "data": shift_schedules_data_2021,
            "options": options
        }

        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ShiftSchedule.objects.count(), 1)
        self.assertEqual(ShiftScheduleDay.objects.count(), 3)
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDay": {
                "created": 3
            },
            "ShiftSchedule": {
                "created": 1
            }
        })
        shift_schedule = ShiftSchedule.objects.get(code="1")
        self.assertEqual(shift_schedule.employee_id, self.employee.id)

        # с индивид. графиками не до конца понятно, пока их не учитываем
        # resp = self.client.get(
        #     self.get_url('Employee-shift-schedule'),
        #     data={'employee_id': self.employee.id, 'dt__gte': '2021-01-01', 'dt__lte': '2021-01-30'},
        # )
        # self.assertEqual(resp.status_code, 200)
        # resp_data = resp.json()
        # self.assertDictEqual(
        #     resp_data, {
        #         str(self.employee.id): {
        #             "2021-01-01": {
        #                 "day_type": "W",
        #                 "work_hours": 13.0
        #             },
        #             "2021-01-02": {
        #                 "day_type": "H",
        #                 "work_hours": 0.0
        #             },
        #             "2021-01-07": {
        #                 "day_type": "W",
        #                 "work_hours": 12.0
        #             }
        #         }
        #     }
        # )

    def test_batch_update_or_create_shift_schedules_by_code(self):
        shift_schedules_data_2021 = [
            {
                "code": "1",
                "name": "График 1",
                "days": [
                    {
                        "code": "1_2021-01-01",
                        "dt": "2021-01-01",
                        "day_type": 'W',
                        "work_hours": Decimal("13.00"),
                    },
                    {
                        "code": "1_2021-01-02",
                        "dt": "2021-01-02",
                        "day_type": 'H',
                        "work_hours": Decimal("0.00"),
                    },
                    {
                        "code": "1_2021-01-07",
                        "dt": "2021-01-07",
                        "day_type": 'W',
                        "work_hours": Decimal("12.00"),
                    },
                ]
            }
        ]
        options = {
            "by_code": True,
            "return_response": True,
            "delete_scope_fields_list": ["code"],
        }
        data = {
            "data": shift_schedules_data_2021,
            "options": options
        }

        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ShiftSchedule.objects.count(), 1)
        self.assertEqual(ShiftScheduleDay.objects.count(), 3)
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDay": {
                "created": 3
            },
            "ShiftSchedule": {
                "created": 1
            }
        })

        shift_schedules_data_2021[0]['days'][0]['work_hours'] += Decimal('3.00')
        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDay": {
                "skipped": 2,
                "updated": 1
            },
            "ShiftSchedule": {
                "skipped": 1
            }
        })
        self.assertEqual(ShiftScheduleDay.objects.get(code='1_2021-01-01').work_hours, 16)

        shift_schedules_data_2021[0]['days'].append(
            {
                "code": "1_2021-01-08",
                "dt": "2021-01-08",
                "day_type": 'W',
                "work_hours": Decimal("12.00"),
            },
        )
        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDay": {
                "created": 1,
                "skipped": 3
            },
            "ShiftSchedule": {
                "skipped": 1
            }
        })

        shift_schedule = ShiftSchedule.objects.first()
        shift_schedule.code = None
        shift_schedule.save()

        del_data = {"data": [], "options": options}
        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(del_data),
            content_type='application/json')
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {'ShiftSchedule': {}})  # не удаляется вручную созданная (без code)

        shift_schedule.code = '1'
        shift_schedule.save()

        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(del_data),
            content_type='application/json')
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftSchedule": {}
        })


class TestShiftScheduleIntervalViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.user = UserFactory(network=cls.network)
        cls.shop = ShopFactory(
            network=cls.network,
            tm_open_dict='{"0": "08:00:00","1": "08:00:00","2": "08:00:00","3": "08:00:00","4": "08:00:00"}',
            tm_close_dict='{"0": "20:00:00","1": "20:00:00","2": "20:00:00","3": "20:00:00","4": "19:00:00"}',
        )
        cls.group = GroupFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user)
        cls.employment = EmploymentFactory(
            employee=cls.employee, shop=cls.shop, function_group=cls.group)
        cls.add_group_perm(cls.group, 'ShiftScheduleInterval_batch_update_or_create', 'POST')
        cls.add_group_perm(cls.group, 'ShiftSchedule_batch_update_or_create', 'POST')
        cls.add_group_perm(cls.group, 'Employee_shift_schedule', 'GET')

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.shop.refresh_from_db()

    def test_shift_schedule_interval_integration_for_employees(self):
        empl2 = EmployeeFactory(user=self.user, code='empl2', tabel_code='empl2')
        empl3 = EmployeeFactory(user=self.user, code='empl3', tabel_code='empl3')

        shift_schedules_data_2021 = [
            {
                "code": "1",
                "name": "График 1",
                "days": [
                    {
                        "code": "1_2021-01-01",
                        "dt": "2021-01-01",
                        "day_type": "W",
                        "work_hours": "11",
                        "day_hours": "11",
                        "night_hours": "0",
                    },
                    {
                        "code": "1_2021-01-07",
                        "dt": "2021-01-07",
                        "day_type": "W",
                        "work_hours": "13",
                        "day_hours": "13",
                        "night_hours": "0",
                    },
                ]
            },
            {
                "code": "2",
                "name": "График 2",
                "days": [
                    {
                        "code": "2_2021-01-01",
                        "dt": "2021-01-01",
                        "day_type": "W",
                        "work_hours": "11",
                        "day_hours": "11",
                        "night_hours": "0",
                    },
                    {
                        "code": "2_2021-01-07",
                        "dt": "2021-01-07",
                        "day_type": "W",
                        "work_hours": "13",
                        "day_hours": "13",
                        "night_hours": "0",
                    },
                ]
            },
            {
                "code": "3",
                "name": "График 3",
                "days": [
                    {
                        "code": "3_2022-01-01",
                        "dt": "2022-01-01",
                        "day_type": "W",
                        "work_hours": "16",
                        "day_hours": "16",
                        "night_hours": "0",
                    },
                    {
                        "code": "3_2022-01-07",
                        "dt": "2022-01-07",
                        "day_type": "W",
                        "work_hours": "11",
                        "day_hours": "11",
                        "night_hours": "0",
                    },
                ]
            }
        ]
        shift_schedules_options = {
            "by_code": True,
            "return_response": True,
            "delete_scope_fields_list": ["code"],
        }
        data = {
            "data": shift_schedules_data_2021,
            "options": shift_schedules_options
        }

        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)

        shift_schedule_intervals_data = [
            {
                "code": "empl2_1_2021-01-01",
                "shift_schedule__code": "1",
                "employee__tabel_code": "empl2",
                "dt_start": "2021-01-01",
                "dt_end": "2021-01-05",
            },
            {
                "code": "empl2_2_2021-01-01",
                "shift_schedule__code": "2",
                "employee__tabel_code": "empl2",
                "dt_start": "2021-01-06",
                "dt_end": "2021-12-31",
            },
            {
                "code": "empl3_1_2021-01-01",
                "shift_schedule__code": "1",
                "employee__tabel_code": "empl3",
                "dt_start": "2021-01-01",
                "dt_end": "2021-12-31",
            }
        ]

        shift_schedule_intervals_options = {
            "by_code": True,
            "delete_scope_fields_list": [
                "employee_id",
            ],
        }

        data = {
            'data': shift_schedule_intervals_data,
            'options': shift_schedule_intervals_options,
        }
        resp = self.client.post(
            self.get_url('ShiftScheduleInterval-batch-update-or-create'), self.dump_data(data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data, {
            "stats": {
                "ShiftScheduleInterval": {
                    "created": 3
                }
            }
        })
        self.assertEqual(ShiftScheduleInterval.objects.count(), 3)

        shift_schedule_intervals_data.append(
            {
                "code": "empl3_3_2022-01-01",
                "shift_schedule__code": "3",
                "employee__tabel_code": "empl3",
                "dt_start": "2022-01-01",
                "dt_end": "2022-12-31",
            }
        )
        resp = self.client.post(
            self.get_url('ShiftScheduleInterval-batch-update-or-create'), self.dump_data(data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data, {
            "stats": {
                "ShiftScheduleInterval": {
                    "skipped": 3,
                    "created": 1,
                }
            }
        })

        resp = self.client.get(
            self.get_url('Employee-shift-schedule'),
            data={'employee_id': empl2.id, 'dt__gte': '2021-01-01', 'dt__lte': '2021-01-01'},
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data, {
                str(empl2.id): {
                    "2021-01-01": {
                        "day_type": "W",
                        "work_hours": 11.0,
                        "day_hours": 11.0,
                        "night_hours": 0.0,
                    }
                }
            }
        )

        shift_schedule_intervals_data2 = [
            {
                "code": "empl2_3_2022-01-01",
                "shift_schedule__code": "3",
                "employee__tabel_code": "empl2",
                "dt_start": "2022-01-01",
                "dt_end": "2022-12-31",
            }
        ]
        shift_schedule_intervals_options2 = {
            "by_code": True,
            "delete_scope_fields_list": [
                "employee_id",
            ],
        }
        data2 = {
            'data': shift_schedule_intervals_data2,
            'options': shift_schedule_intervals_options2,
        }
        resp = self.client.post(
            self.get_url('ShiftScheduleInterval-batch-update-or-create'), self.dump_data(data2),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data, {
            "stats": {
                "ShiftScheduleInterval": {
                    "created": 1,
                    "deleted": 2,
                }
            }
        })

        resp = self.client.get(
            self.get_url('Employee-shift-schedule'),
            data={'employee_id': empl2.id, 'dt__gte': '2022-01-01', 'dt__lte': '2022-01-30'},
        )
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(
            resp_data, {
                str(empl2.id): {
                    "2022-01-01": {
                        "day_type": "W",
                        "work_hours": 16.0,
                        "day_hours": 16.0,
                        "night_hours": 0.0,
                    },
                    "2022-01-07": {
                        "day_type": "W",
                        "work_hours": 11.0,
                        "day_hours": 11.0,
                        "night_hours": 0.0,
                    }
                }
            }
        )
