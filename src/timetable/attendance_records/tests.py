from datetime import datetime, date, time, timedelta

from rest_framework.test import APITestCase

from src.base.tests.factories import (
    ShopFactory,
    UserFactory,
    GroupFactory,
    EmploymentFactory,
    NetworkFactory,
    EmployeeFactory,
    WorkerPositionFactory,
    BreakFactory,
)
from src.timetable.models import AttendanceRecords
from src.util.mixins.tests import TestsHelperMixin


class AttendanceRecordsViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        breaks = BreakFactory(value='[[0, 2040, [60]]]', code='1h')
        cls.network = NetworkFactory(breaks=breaks)
        cls.root_shop = ShopFactory(
            network=cls.network,
            settings__breaks=breaks,
        )
        cls.shop = ShopFactory(
            parent=cls.root_shop,
            name='SHOP_NAME',
            network=cls.network,
            email='shop@example.com',
            settings__breaks=breaks,
        )
        cls.user = UserFactory(email='worker@example.com', network=cls.network)
        cls.user2 = UserFactory(email='worker2@example.com', network=cls.network)
        cls.user3 = UserFactory(email='worker3@example.com', network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user)
        cls.employee2 = EmployeeFactory(user=cls.user2)
        cls.employee3 = EmployeeFactory(user=cls.user3)
        cls.group = GroupFactory(name='Сотрудник', network=cls.network)
        cls.position = WorkerPositionFactory(
            name='Работник', group=cls.group,
            breaks=breaks,
        )
        cls.employment = EmploymentFactory(
            employee=cls.employee, shop=cls.shop, position=cls.position,
        )
        cls.employment2 = EmploymentFactory(
            employee=cls.employee2, shop=cls.shop, position=cls.position,
        )
        cls.employment3 = EmploymentFactory(
            employee=cls.employee3, shop=cls.shop, position=cls.position,
        )
        cls.add_group_perm(cls.group, 'AttendanceRecords', 'GET')
        cls.dt = date(2021, 5, 1)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def _create_attendance_records_pair(self, user, dt=None, coming_time=None, leaving_time=None):
        dt = dt or self.dt
        coming_time = coming_time or time(10)
        leaving_time = leaving_time or time(20)
        coming = AttendanceRecords.objects.create(
            shop=self.shop,
            type=AttendanceRecords.TYPE_COMING,
            user=user,
            dttm=datetime.combine(dt, coming_time),
        )
        leaving = AttendanceRecords.objects.create(
            shop=self.shop,
            type=AttendanceRecords.TYPE_LEAVING,
            user=user,
            dttm=datetime.combine(dt, leaving_time),
        )
        return coming, leaving

    def test_list(self):
        ar_coming, _ar_leaving = self._create_attendance_records_pair(self.user)
        self.assertEqual(ar_coming.employee_id, self.employee.id)
        self._create_attendance_records_pair(self.user2)
        self._create_attendance_records_pair(self.user3)
        resp = self.client.get(self.get_url('AttendanceRecords-list'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 6)

        # фильтр по сотрудникам
        resp = self.client.get(
            self.get_url('AttendanceRecords-list') + f'?employee_id__in={self.employee.id},{self.employee2.id}')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 4)

        # фильтр по сотрудникам и типу
        resp = self.client.get(
            self.get_url('AttendanceRecords-list') + f'?employee_id__in={self.employee.id},{self.employee2.id}&type=C')
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 2)

        # фильтр по дате
        resp = self.client.get(
            self.get_url('AttendanceRecords-list'), data={'dt__gte': self.dt + timedelta(days=1)})
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 0)
