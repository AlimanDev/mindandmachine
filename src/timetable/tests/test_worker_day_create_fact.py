from datetime import time, datetime

from django.utils.timezone import now
from rest_framework import status
from rest_framework.test import APITestCase

from src.timetable.models import (
    WorkerDay,
    WorkType,
    WorkTypeName,
)
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


class TestWorkerDayCreateFact(TestsHelperMixin, APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.url = '/rest_api/worker_day/'
        cls.url_approve = '/rest_api/worker_day/approve/'
        cls.dt = now().date()
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_fact(self):
        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(8, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        # create not approved fact
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        fact_id = response.json()['id']

        # create not approved plan
        data['is_fact'] = False
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        plan_id = response.json()['id']

    def test_closest_plan_approved_set_on_fact_creation(self):
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(10, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(12, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )
        plan_approved2 = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(12, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(12, 1, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(14, 5, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        resp = self.client.post(self.url, self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        fact_id = resp.json()['id']
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.closest_plan_approved_id, plan_approved2.id)

    def test_closest_plan_approved_set_on_fact_creation_when_single_plan_far_from_fact(self):
        plan_approved = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(8, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(20, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(12, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        resp = self.client.post(self.url, self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        fact_id = resp.json()['id']
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.closest_plan_approved_id, plan_approved.id)

    def test_closest_plan_approved_not_set_on_fact_creation_when_multiple_plan_exists(self):
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(10, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(14, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )
        WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            dt=self.dt,
            employee=self.employee2,
            employment=self.employment2,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt, time(18, 0, 0)),
            dttm_work_end=datetime.combine(self.dt, time(21, 0, 0)),
            cashbox_details__work_type=self.work_type,
        )

        data = {
            "shop_id": self.shop.id,
            "employee_id": self.employee2.id,
            "employment_id": self.employment2.id,
            "dt": self.dt,
            "is_fact": True,
            "type": WorkerDay.TYPE_WORKDAY,
            "dttm_work_start": datetime.combine(self.dt, time(12, 0, 0)),
            "dttm_work_end": datetime.combine(self.dt, time(20, 0, 0)),
            "worker_day_details": [{
                "work_part": 1.0,
                "work_type_id": self.work_type.id}
            ]
        }

        resp = self.client.post(self.url, self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        fact_id = resp.json()['id']
        fact = WorkerDay.objects.get(id=fact_id)
        self.assertEqual(fact.closest_plan_approved_id, None)
