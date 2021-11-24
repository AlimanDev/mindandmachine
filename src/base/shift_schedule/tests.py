from rest_framework.test import APITestCase

from src.base.models import (
    ShiftSchedule,
    ShiftScheduleDay,
    ShiftScheduleDayItem,
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
            "delete_scope_fields_list": ["year", "code__isnull"],
            "delete_scope_values_list": [
                {
                    "year": 2021,
                    "code__isnull": False
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
