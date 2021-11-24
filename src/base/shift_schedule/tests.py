from rest_framework.test import APITestCase

from src.base.models import (
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleDayItem,
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
        cls.employee = EmployeeFactory(user=cls.user)
        cls.employment = EmploymentFactory(
            employee=cls.employee, shop=cls.shop, function_group=cls.group)
        cls.add_group_perm(cls.group, 'ShiftSchedule_batch_update_or_create', 'POST')

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.shop.refresh_from_db()

    def test_batch_update_or_create_shift_schedules_by_code(self):
        shift_schedules_data_2021 = [
            {
                "code": "1",
                "name": "График 1",
                "year": 2021,
                "days": [
                    {
                        "code": "1_2021-01-01",
                        "dt": "2021-01-01",
                        "items": [
                            {
                                "code": "1_2021-01-01_D",
                                "hours_type": "D",
                                "hours_amount": 8
                            },
                            {
                                "code": "1_2021-01-01_N",
                                "hours_type": "N",
                                "hours_amount": 3
                            }
                        ],
                    },
                    {
                        "code": "1_2021-01-07",
                        "dt": "2021-01-07",
                        "items": [
                            {
                                "code": "1_2021-01-07_D",
                                "hours_type": "D",
                                "hours_amount": 13
                            }
                        ],
                    },
                ]
            }
        ]
        options = {
            "by_code": True,
            "return_response": True,
            "delete_scope_fields_list": ["year"],
            "delete_scope_values_list": [
                {
                    "year": 2021,
                }
            ],
        }
        data = {
            "data": shift_schedules_data_2021,
            "options": options
        }

        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(ShiftSchedule.objects.count(), 1)
        self.assertEqual(ShiftScheduleDay.objects.count(), 2)
        self.assertEqual(ShiftScheduleDayItem.objects.count(), 3)
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDayItem": {
                "created": 3
            },
            "ShiftScheduleDay": {
                "created": 2
            },
            "ShiftSchedule": {
                "created": 1
            }
        })

        shift_schedules_data_2021[0]['days'][1]['items'].append({
            "code": "1_2021-01-07_N",
            "hours_type": "N",
            "hours_amount": 3
        })
        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDayItem": {
                "updated": 3,
                "created": 1
            },
            "ShiftScheduleDay": {
                "updated": 2
            },
            "ShiftSchedule": {
                "updated": 1
            }
        })

        shift_schedules_data_2021[0]['days'][0]['items'][0]['hours_amount'] = 22
        resp = self.client.post(
            self.get_url('ShiftSchedule-batch-update-or-create'), self.dump_data(data), content_type='application/json')
        resp_data = resp.json()
        self.assertDictEqual(resp_data['stats'], {
            "ShiftScheduleDayItem": {
                "updated": 4  # TODO: добавить skipped?
            },
            "ShiftScheduleDay": {
                "updated": 2
            },
            "ShiftSchedule": {
                "updated": 1
            }
        })
        self.assertEqual(ShiftScheduleDayItem.objects.get(code='1_2021-01-01_D').hours_amount, 22)

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
            "ShiftScheduleDayItem": {
                "deleted": 4
            },
            "ShiftScheduleDay": {
                "deleted": 2
            },
            "ShiftSchedule": {
                "deleted": 1
            }
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

    def setUp(self):
        self.client.force_authenticate(user=self.user)
        self.shop.refresh_from_db()

    def test_shift_schedule_interval_integration_for_employees(self):
        EmployeeFactory(user=self.user, code='empl2', tabel_code='empl2')
        EmployeeFactory(user=self.user, code='empl3', tabel_code='empl3')

        shift_schedules_data_2021 = [
            {
                "code": "1",
                "name": "График 1",
                "year": 2021,
                "days": [
                    {
                        "code": "1_2021-01-01",
                        "dt": "2021-01-01",
                        "items": [
                            {
                                "code": "1_2021-01-01_D",
                                "hours_type": "D",
                                "hours_amount": 8
                            },
                            {
                                "code": "1_2021-01-01_N",
                                "hours_type": "N",
                                "hours_amount": 3
                            }
                        ],
                    },
                    {
                        "code": "1_2021-01-07",
                        "dt": "2021-01-07",
                        "items": [
                            {
                                "code": "1_2021-01-07_D",
                                "hours_type": "D",
                                "hours_amount": 13
                            }
                        ],
                    },
                ]
            },
            {
                "code": "2",
                "name": "График 2",
                "year": 2021,
                "days": [
                    {
                        "code": "2_2021-01-01",
                        "dt": "2021-01-01",
                        "items": [
                            {
                                "code": "2_2021-01-01_D",
                                "hours_type": "D",
                                "hours_amount": 12
                            },
                            {
                                "code": "2_2021-01-01_N",
                                "hours_type": "N",
                                "hours_amount": 1
                            }
                        ],
                    },
                    {
                        "code": "2_2021-01-07",
                        "dt": "2021-01-07",
                        "items": [
                            {
                                "code": "2_2021-01-07_D",
                                "hours_type": "D",
                                "hours_amount": 13
                            }
                        ],
                    },
                ]
            },
            {
                "code": "3",
                "name": "График 3",
                "year": 2022,
                "days": [
                    {
                        "code": "3_2022-01-01",
                        "dt": "2022-01-01",
                        "items": [
                            {
                                "code": "3_2022-01-01_D",
                                "hours_type": "D",
                                "hours_amount": 12
                            },
                            {
                                "code": "3_2022-01-01_N",
                                "hours_type": "N",
                                "hours_amount": 4
                            }
                        ],
                    },
                    {
                        "code": "3_2022-01-07",
                        "dt": "2022-01-07",
                        "items": [
                            {
                                "code": "3_2022-01-07_D",
                                "hours_type": "D",
                                "hours_amount": 11
                            }
                        ],
                    },
                ]
            }
        ]
        shift_schedules_options = {
            "by_code": True,
            "return_response": True,
            "delete_scope_fields_list": ["year"],
            "delete_scope_values_list": [
                {
                    "year": 2021,
                }
            ],
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
                "dt_start": "2021-01-01",
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
                "shift_schedule__year__in",
            ],
            "delete_scope_values_list": [
                {
                    "shift_schedule__year__in": [2020, 2021, 2022],
                }
            ]
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
                    "updated": 3,
                    "created": 1,
                }
            }
        })

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
                "shift_schedule__year__in",
            ],
            "delete_scope_values_list": [
                {
                    "shift_schedule__year__in": [2022],
                }
            ]
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
                    "deleted": 1,
                }
            }
        })

        shift_schedule_intervals_options2['delete_scope_values_list'][0]['shift_schedule__year__in'] = [2021, 2022]
        resp = self.client.post(
            self.get_url('ShiftScheduleInterval-batch-update-or-create'), self.dump_data(data2),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertDictEqual(resp_data, {
            "stats": {
                "ShiftScheduleInterval": {
                    "updated": 1,
                    "deleted": 3,
                }
            }
        })
