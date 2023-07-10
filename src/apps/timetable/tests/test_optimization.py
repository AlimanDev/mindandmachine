from datetime import date, time, datetime, timedelta
from django.conf import settings

from rest_framework.test import APITestCase
from src.apps.timetable.models import (
    WorkerDay,
)
from src.apps.timetable.worker_day.services.approve import WorkerDayApproveService
from src.common.mixins.tests import TestsHelperMixin


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
        For checking specific parts of the code use decorator at `src.common.decorators.print_queries`.
        """
        QUERY_COUNT = 38
        WORKERDAYS_COUNT = 20
        for dt in (self.today + timedelta(i) for i in range(WORKERDAYS_COUNT)):
            WorkerDay.objects.create(
                dt=dt,
                employment=self.employment2,
                employee=self.employee2,
                shop=self.shop,
                type_id=WorkerDay.TYPE_WORKDAY,
                dttm_work_start=datetime.combine(dt, time(9)),
                dttm_work_end=datetime.combine(dt, time(18)),
                is_fact=False,
                is_approved=False,
            )
        kwargs = {
            'is_fact': False,
            'dt_from': self.today,
            'dt_to': self.today + timedelta(WORKERDAYS_COUNT - 1),
            'user': self.user1,
            'shop_id': self.shop.id,
            'employee_ids': None,
            'wd_types': [WorkerDay.TYPE_WORKDAY, WorkerDay.TYPE_HOLIDAY],  
            'approve_open_vacs': True,
            'exclude_approve_q': None
        }
        settings.DEBUG = True
        with self.assertNumQueries(QUERY_COUNT):
            count = WorkerDayApproveService(**kwargs).approve()
            self.assertEqual(count, WORKERDAYS_COUNT)
        self.assertEqual(WorkerDay.objects.filter(is_approved=True).count(), WORKERDAYS_COUNT)
