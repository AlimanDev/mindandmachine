from datetime import timedelta, date

from rest_framework.test import APITestCase

from src.base.models import WorkerPosition, Employment
from src.timetable.models import WorkTypeName, WorkType, EmploymentWorkType, WorkerDay
from src.util.mixins.tests import TestsHelperMixin


class TestEmploymentAPI(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.wt_name = WorkTypeName.objects.create(name='test_name', code='test_code')
        cls.wt_name2 = WorkTypeName.objects.create(name='test_name2', code='test_code2')
        cls.work_type1 = WorkType.objects.create(work_type_name=cls.wt_name, shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(work_type_name=cls.wt_name2, shop=cls.shop)
        cls.work_type3 = WorkType.objects.create(work_type_name=cls.wt_name, shop=cls.shop2)
        cls.position1 = WorkerPosition.objects.create(network=cls.network, name='Test1')
        cls.position2 = WorkerPosition.objects.create(network=cls.network, name='Test2')
        Employment.objects.filter(
            pk__in=[
                cls.employment1.id,
                cls.employment2.id,
                cls.employment3.id,
                cls.employment4.id,
            ]
        ).update(position=cls.position1)
        Employment.objects.filter(
            pk__in=[
                cls.employment5.id,
                cls.employment6.id,
                cls.employment7.id,
            ]
        ).update(position=cls.position2)
        EmploymentWorkType.objects.create(
            employment=cls.employment1,
            work_type=cls.work_type1,
        )
        EmploymentWorkType.objects.create(
            employment=cls.employment2,
            work_type=cls.work_type3,
        )
        EmploymentWorkType.objects.create(
            employment=cls.employment3,
            work_type=cls.work_type2,
        )
        EmploymentWorkType.objects.create(
            employment=cls.employment4,
            work_type=cls.work_type1,
        )
        EmploymentWorkType.objects.create(
            employment=cls.employment5,
            work_type=cls.work_type3,
        )
        EmploymentWorkType.objects.create(
            employment=cls.employment6,
            work_type=cls.work_type1,
        )
        EmploymentWorkType.objects.create(
            employment=cls.employment7,
            work_type=cls.work_type1,
        )
        cls.url = '/rest_api/user/'

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_shop_id__in_filter(self):
        response = self.client.get(
            self.url,
        )
        self.assertEqual(len(response.json()), 8)
        response = self.client.get(
            self.url + f'?shop_id__in={self.root_shop.id}',
        )
        self.assertEqual(len(response.json()), 1)
        response = self.client.get(
            self.url + f'?shop_id__in={self.root_shop.id},{self.shop.id}',
        )
        self.assertEqual(len(response.json()), 6)

    def test_position_id__in_filter(self):
        response = self.client.get(
            self.url,
        )
        self.assertEqual(len(response.json()), 8)
        response = self.client.get(
            self.url + f'?position_id__in={self.position1.id}',
        )
        self.assertEqual(len(response.json()), 4)
        response = self.client.get(
            self.url + f'?position_id__in={self.position1.id},{self.position2.id}',
        )
        self.assertEqual(len(response.json()), 7)

    def test_work_type_id__in_filter(self):
        response = self.client.get(
            self.url,
        )
        self.assertEqual(len(response.json()), 8)
        response = self.client.get(
            self.url + f'?work_type_id__in={self.wt_name.id}',
        )
        self.assertEqual(len(response.json()), 6)
        response = self.client.get(
            self.url + f'?work_type_id__in={self.wt_name.id},{self.wt_name2.id}',
        )
        self.assertEqual(len(response.json()), 7)

    def test_worker_day__in_filter(self):
        response = self.client.get(
            self.url,
        )
        dt_now = date.today()
        self.assertEqual(len(response.json()), 8)
        WorkerDay.objects.create(
            employee=self.employee1,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt_now,
        )
        WorkerDay.objects.create(
            employee=self.employee2,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt_now,
        )
        WorkerDay.objects.create(
            employee=self.employee3,
            type_id=WorkerDay.TYPE_WORKDAY,
            dt=dt_now,
        )
        WorkerDay.objects.create(
            employee=self.employee4,
            type_id=WorkerDay.TYPE_HOLIDAY,
            dt=dt_now + timedelta(days=1),
        )
        response = self.client.get(
            self.url + f'?worker_day_type__in=H&worker_day_dt__in={dt_now}',
        )
        self.assertEqual(len(response.json()), 2)
        response = self.client.get(
            self.url + f'?worker_day_type__in=H,W&worker_day_dt__in={dt_now}',
        )
        self.assertEqual(len(response.json()), 3)
        response = self.client.get(
            self.url + f'?worker_day_type__in=H,W&worker_day_dt__in={dt_now},{dt_now + timedelta(days=1)}',
        )
        self.assertEqual(len(response.json()), 4)
