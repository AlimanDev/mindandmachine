import datetime

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from src.timetable.models import WorkerDay, WorkTypeName, WorkType
from src.base.models import Employment
from src.recognition.models import TickPoint
from src.util.mixins.tests import TestsHelperMixin


class TestWorkShiftViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
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
            "dttm_work_start": (expected_start - datetime.timedelta(
                hours=self.shop2.get_tz_offset())).isoformat() if expected_start else None,
            "dttm_work_end": (expected_end - datetime.timedelta(
                hours=self.shop2.get_tz_offset())).isoformat() if expected_end else None
        }
        if expected_shop_code:
            exp_resp['shop'] = expected_shop_code
        self.assertDictEqual(resp.json(), exp_resp)

    def test_work_shift(self):
        self._test_work_shift(self.dt_str, self.user2.username, None, None)

        dttm_start = datetime.datetime.combine(self.today, datetime.time(10))
        wd = WorkerDay.objects.create(
            dttm_work_start=dttm_start,
            dttm_work_end=None,
            type=WorkerDay.TYPE_WORKDAY,
            is_fact=True,
            is_approved=True,
            dt=self.dt_str,
            shop=self.work_type1.shop,
            employee=self.employee2,
            employment=self.employment2,
        )
        self._test_work_shift(self.dt_str, self.user2.username, dttm_start, None, self.shop2.code)

        dttm_end = datetime.datetime.combine(self.today, datetime.time(20))
        wd.dttm_work_end = dttm_end
        wd.save()
        self._test_work_shift(self.dt_str, self.user2.username, dttm_start, dttm_end, self.shop2.code)

    def test_cant_get_work_shift_for_someones_user(self):
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-work-shift'),
            data={'dt': self.dt_str, 'worker': self.user3.username},
        )
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


    def test_no_active_employee(self):
        t = TickPoint.objects.create(
            network=self.network,
            name='test',
            shop=self.shop,
        )

        response = self.client.post(
            path='/api/v1/token-auth/',
            data={
                'key': t.key,
            }
        )

        token = response.json()['token']
        self.client.defaults['HTTP_AUTHORIZATION'] = 'Token %s' % token
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
        )
        self.assertEqual(len(resp.json()), 5)
        Employment.objects.all().update(dt_hired=datetime.date.today() + datetime.timedelta(1), dt_fired=None)
        resp = self.client.get(
            self.get_url('TimeAttendanceWorkerDay-list'),
        )
        self.assertEqual(len(resp.json()), 0)
