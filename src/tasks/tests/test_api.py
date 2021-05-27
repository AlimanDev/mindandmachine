from datetime import timedelta, datetime, time
from uuid import uuid4

from django.utils import timezone
from rest_framework.test import APITestCase

from src.base.tests.factories import (
    NetworkFactory, UserFactory, EmploymentFactory, ShopFactory, EmployeeFactory, GroupFactory
)
from src.forecast.models import OperationTypeName, OperationType
from src.util.mixins.tests import TestsHelperMixin
from src.util.models_converter import Converter
from ..models import Task


class TestTasksViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.shop = ShopFactory()
        cls.shop2 = ShopFactory()
        cls.operation_type_name = OperationTypeName.objects.create(
            name='Прием врача',
            code='0005',
            network=cls.network,
        )
        cls.operation_type_name2 = OperationTypeName.objects.create(
            name='Другая операция',
            code='0006',
            network=cls.network,
        )
        cls.operation_type = OperationType.objects.create(
            operation_type_name=cls.operation_type_name,
            shop=cls.shop,
        )
        cls.group_admin = GroupFactory(code='admin', name='Администратор')
        cls.user_admin = UserFactory()
        cls.employee_admin = EmployeeFactory(user=cls.user_admin)
        cls.employment_admin = EmploymentFactory(employee=cls.employee_admin, shop=cls.shop,
                                                 function_group=cls.group_admin)
        cls.add_group_perm(cls.group_admin, 'Task', 'GET')
        cls.add_group_perm(cls.group_admin, 'Task', 'PUT')
        cls.add_group_perm(cls.group_admin, 'Task', 'POST')
        cls.add_group_perm(cls.group_admin, 'Task', 'DELETE')

        cls.group_worker = GroupFactory(code='worker', name='Сотрудник')
        cls.user_worker = UserFactory()
        cls.worker_tabel_code = '0000-0001'
        cls.employee_worker = EmployeeFactory(user=cls.user_worker, tabel_code=cls.worker_tabel_code)
        cls.employment_worker = EmploymentFactory(employee=cls.employee_worker, shop=cls.shop,
                                                  function_group=cls.group_worker)

        cls.user_worker2 = UserFactory()
        cls.worker_tabel_code2 = '0000-0002'
        cls.employee_worker2 = EmployeeFactory(user=cls.user_worker2, tabel_code=cls.worker_tabel_code2)
        cls.employment_worker2 = EmploymentFactory(employee=cls.employee_worker2, shop=cls.shop2,
                                                  function_group=cls.group_worker)
        cls.dt_now = timezone.now().date()

    def setUp(self) -> None:
        self.client.force_authenticate(user=self.user_admin)

    def _get_task_data(self, override_kwargs: dict = None):
        task_code = uuid4()
        task_data = {
            "code": task_code,
            "dttm_event": datetime.combine(self.dt_now - timedelta(days=1), time(9)),
            "tabel_code": self.worker_tabel_code,
            "shop_code": self.shop.code,
            "dttm_start_time": datetime.combine(self.dt_now, time(10)),
            "dttm_end_time": datetime.combine(self.dt_now, time(11)),
            "operation_type_code": self.operation_type_name.code,
            "by_code": True,
        }
        if override_kwargs:
            task_data.update(override_kwargs)
        return task_data

    def test_get_tasks(self):
        for n in range(10, 20):
            dttm_start_time = datetime.combine(self.dt_now, time(n, 0, 0))
            Task.objects.create(
                employee=self.employee_worker,
                operation_type=self.operation_type,
                dt=self.dt_now,
                dttm_start_time=dttm_start_time,
                dttm_end_time=dttm_start_time + timedelta(hours=1),
            )
        resp = self.client.get(
            path=self.get_url('Task-list'),
            data=dict(
                shop_id=self.shop.id,
                dt__gte=Converter.convert_date(self.dt_now),
                dt__lte=Converter.convert_date(self.dt_now),
            ),
        )
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 10)

    def test_create_and_update_with_put_by_code(self):
        task_data = self._get_task_data()

        # create
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        task = Task.objects.filter(id=resp.json()['id']).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.dttm_event, task_data['dttm_event'])
        self.assertEqual(task.dttm_start_time, task_data['dttm_start_time'])
        self.assertEqual(task.dttm_end_time, task_data['dttm_end_time'])
        self.assertEqual(task.dt, task_data['dttm_start_time'].date())

        # update
        task_data['dttm_event'] = task_data['dttm_event'] + timedelta(seconds=5)
        task_data['dttm_end_time'] = datetime.combine(self.dt_now, time(11, 15))
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(id=resp.json()['id']).first()
        self.assertIsNotNone(task)
        self.assertEqual(task.dttm_end_time, task_data['dttm_end_time'])

        # delete
        task_data['dttm_event'] = task_data['dttm_event'] + timedelta(seconds=5)
        resp = self.client.delete(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(code=task_data['code']).first()
        self.assertIsNone(task)  # удален

        # update
        task_data['dttm_event'] = task_data['dttm_event'] + timedelta(seconds=5)
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(code=task_data['code']).first()
        self.assertIsNotNone(task)  # таск восстановлен

    def test_create_operation_type_if_not_exists_on_put(self):
        task_data = self._get_task_data(override_kwargs=dict(operation_type_code=self.operation_type_name2.code))

        # create
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)
        task = Task.objects.filter(id=resp.json()['id']).first()
        self.assertIsNotNone(task)
        operation_type = OperationType.objects.filter(
            shop__code=task_data['shop_code'],
            operation_type_name__code=task_data['operation_type_code'],
        ).first()
        resp_data = resp.json()
        self.assertEqual(resp_data['operation_type']['id'], operation_type.id)

    def test_skip_update_if_requests_order_is_wrong(self):
        """
        Последовательность событий:
        1. Создание таска
        2. Обновление таска
        3. Удаление таска

        Последовательность запросов:
        1. Создание таска
        2. Удаление таска
        3. Обновление таска -- должен быть проигнорирован
        """
        task_data = self._get_task_data()
        # create
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)

        # delete
        task_data['dttm_event'] = task_data['dttm_event'] + timedelta(seconds=5)
        resp = self.client.delete(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(code=task_data['code']).first()
        self.assertIsNone(task)

        # update
        task_data['dttm_event'] = task_data['dttm_event'] - timedelta(seconds=2)
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(code=task_data['code']).first()
        self.assertIsNone(task)  # все еще удален

    def test_skip_delete_if_requests_order_is_wrong(self):
        """
        Последовательность событий:
        1. Создание таска
        2. Удаление таска
        3. Обновление таска

        Последовательность запросов:
        1. Создание таска
        2. Обновление таска
        3. Удаление таска -- должен быть проигнорирован
        """
        task_data = self._get_task_data()
        # create
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 201)

        # update
        task_data['dttm_event'] = task_data['dttm_event'] + timedelta(seconds=5)
        resp = self.client.put(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(code=task_data['code']).first()
        self.assertIsNotNone(task)

        # delete
        task_data['dttm_event'] = task_data['dttm_event'] - timedelta(seconds=2)
        resp = self.client.delete(
            path=self.get_url('Task-detail', pk=task_data['code']),
            data=self.dump_data(task_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)
        task = Task.objects.filter(code=task_data['code']).first()
        self.assertIsNotNone(task)  # не удален

    def test_filter_by_shop_id(self):
        self.operation_type2 = OperationType.objects.create(
            operation_type_name=self.operation_type_name2,
            shop=self.shop2,
        )
        for n in range(10, 20):
            dttm_start_time = datetime.combine(self.dt_now, time(n, 0, 0))
            Task.objects.create(
                employee=self.employee_worker,
                operation_type=self.operation_type,
                dt=self.dt_now,
                dttm_start_time=dttm_start_time,
                dttm_end_time=dttm_start_time + timedelta(hours=1),
            )
        for n in range(10, 15):
            dttm_start_time = datetime.combine(self.dt_now, time(n, 0, 0))
            Task.objects.create(
                employee=self.employee_worker2,
                operation_type=self.operation_type2,
                dt=self.dt_now,
                dttm_start_time=dttm_start_time,
                dttm_end_time=dttm_start_time + timedelta(hours=1),
            )
        resp = self.client.get(
            path=self.get_url('Task-list'),
            data=dict(
                dt__gte=Converter.convert_date(self.dt_now),
                dt__lte=Converter.convert_date(self.dt_now),
            ),
        )
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 15)

        resp = self.client.get(
            path=self.get_url('Task-list'),
            data=dict(
                shop_id=self.shop.id,
                dt__gte=Converter.convert_date(self.dt_now),
                dt__lte=Converter.convert_date(self.dt_now),
            ),
        )
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 10)

        resp = self.client.get(
            path=self.get_url('Task-list'),
            data=dict(
                shop_id=self.shop2.id,
                dt__gte=Converter.convert_date(self.dt_now),
                dt__lte=Converter.convert_date(self.dt_now),
            ),
        )
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 5)
