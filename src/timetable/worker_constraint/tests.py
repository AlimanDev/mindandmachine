import json

from rest_framework import status
from rest_framework.test import APITestCase

from src.timetable.models import WorkerConstraint
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter


class TestWorkerConstraint(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user1)

    def test_create_and_update_employment_constraints(self):
        wc = WorkerConstraint.objects.create(
            shop=self.shop,
            employment=self.employment1,
            worker_id=self.employment1.employee.user_id,
            weekday=3,
            is_lite=True,
            tm=Converter.parse_time("09:00:00")
        )

        data = {
            'data': [
                {
                    "id": wc.id,
                    "tm": "09:00:00",
                    "is_lite": True,
                    "weekday": 3,
                },
                {
                    "tm": "10:00:00",
                    "is_lite": False,
                    "weekday": 3,
                },
            ]
        }
        resp = self.client.post(
            self.get_url('WorkerConstraint-list', employment_pk=self.employment1.pk),
            data=json.dumps(data), content_type='application/json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkerConstraint.objects.filter(employment=self.employment1).count(), 2)

        resp = self.client.get(self.get_url('WorkerConstraint-list', employment_pk=self.employment1.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 2)

        resp = self.client.get(self.get_url('WorkerConstraint-list', employment_pk=self.employment2.pk))
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.json()), 0)

        data['data'].pop()
        resp = self.client.post(
            self.get_url('WorkerConstraint-list', employment_pk=self.employment1.pk),
            data=json.dumps(data), content_type='application/json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkerConstraint.objects.filter(employment=self.employment1).count(), 1)

        data['data'].pop()
        resp = self.client.post(
            self.get_url('WorkerConstraint-list', employment_pk=self.employment1.pk),
            data=json.dumps(data), content_type='application/json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(WorkerConstraint.objects.filter(employment=self.employment1).count(), 0)
