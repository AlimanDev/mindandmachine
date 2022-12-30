from datetime import date
from django.conf import settings

from rest_framework.test import APITestCase
from src.timetable.models import (
    WorkerDay,
)
from src.timetable.worker_day.utils.approve import WorkerDayApproveHelper
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


# Code and performance optimization tests

class TestWorkerDayApproveOptimization(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.today = date.today()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user1)

    def test_approve_db_queries_count(self):
        """
        Optimizing approve database requests (N+1, repeating/unnecessary queries, caching etc.).
        Correct `QUERY_COUNT` as needed when you change approve logic.
        For checking specific parts of the code use:
        ```
        from django.db import connection, reset_queries
        from django.conf import settings
        settings.DEBUG = True
        reset_queries()
        ...some_code...
        print(connection.queries))
        print(len(connection.queries))
        ```
        """
        QUERY_COUNT = 64

        WORKERDAYS_COUNT = 10
        WorkerDayFactory.create_batch(
            WORKERDAYS_COUNT,
            dt=self.today,
            shop=self.shop,
            type_id=WorkerDay.TYPE_WORKDAY,
            is_fact=False,
            is_approved=False,
        )
        kwargs = {
            'is_fact': False,
            'dt_from': self.today,
            'dt_to': self.today,
            'user': self.user1,
            'shop_id': self.shop.id,
            'employee_ids': None,
            'wd_types': [WorkerDay.TYPE_WORKDAY, WorkerDay.TYPE_HOLIDAY],  
            'approve_open_vacs': True,
            'any_draft_wd_exists': False,
            'exclude_approve_q': None
        }
        settings.DEBUG = True
        with self.assertNumQueries(QUERY_COUNT):
            WorkerDayApproveHelper(**kwargs).run()
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), WORKERDAYS_COUNT)
