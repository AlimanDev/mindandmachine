from datetime import timedelta, time, datetime, date

from rest_framework.test import APITestCase

from src.common.mixins.tests import TestsHelperMixin
from src.common.models_converter import Converter

class TestUnaccountedOvertimesAPI(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dt = date.today()
        cls.network.only_fact_hours_that_in_approved_plan = True
        cls.network.save()
        pa1 = cls._create_worker_day(
            cls.employment2,
            dttm_work_start=datetime.combine(cls.dt, time(13)),
            dttm_work_end=datetime.combine(cls.dt + timedelta(1), time(1)),
            is_approved=True,
        )
        pa2 = cls._create_worker_day(
            cls.employment3,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            is_approved=True,
        )
        pa3 = cls._create_worker_day(
            cls.employment4,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            is_approved=True,
        )
        # переработка 3 часа
        cls._create_worker_day(
            cls.employment2,
            dttm_work_start=datetime.combine(cls.dt, time(12)),
            dttm_work_end=datetime.combine(cls.dt + timedelta(1), time(3)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa1.id,
        )
        # нет переработки
        cls._create_worker_day(
            cls.employment3,
            dttm_work_start=datetime.combine(cls.dt, time(8)),
            dttm_work_end=datetime.combine(cls.dt, time(20)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa2.id,
        )
        # переработка 1 час
        cls.wd = cls._create_worker_day(
            cls.employment4,
            dttm_work_start=datetime.combine(cls.dt, time(7)),
            dttm_work_end=datetime.combine(cls.dt, time(20, 30)),
            is_approved=True,
            is_fact=True,
            closest_plan_approved_id=pa3.id,
        )

    def setUp(self):
        self.client.force_authenticate(self.user1)

    def test_get_list(self):
        dt = Converter.convert_date(self.dt)

        response = self.client.get(f'/rest_api/worker_day/?shop_id={self.shop.id}&dt={dt}&is_fact=1')
        self.assertEqual(len(response.json()), 3)
        overtimes = list(map(lambda x: (x['employee_id'], x['unaccounted_overtime']), response.json()))
        assert_overtimes = [
            (self.employee2.id, 180.0),
            (self.employee3.id, 0.0),
            (self.employee4.id, 90.0),
        ]
        self.assertEqual(overtimes, assert_overtimes)

    def test_get(self):
        dt = Converter.convert_date(self.dt)

        response = self.client.get(f'/rest_api/worker_day/{self.wd.id}/')
        self.assertEqual(response.json()['unaccounted_overtime'], 90.0)
