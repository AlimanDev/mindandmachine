import tablib

from rest_framework.test import APITestCase
from src.base.models import Group, FunctionGroup
from src.base.admin import FunctionGroupResource
from src.util.mixins.tests import TestsHelperMixin


class TestBreakValidation(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.data = [
            ['WorkerDay', 'GET', None, 1, 100],
            ['WorkerDay', 'POST', None, 1, 100],
            ['WorkType', 'GET', None, 1, 100],
            ['OperationType', 'PUT', 'S', 1, 100],
        ]
        cls.resource = FunctionGroupResource()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_import_function_groups(self):
        group = Group.objects.create(
            name='Test',
            network=self.network,
        )
        self.assertEqual(FunctionGroup.objects.filter(group=group).count(), 0)
        dataset = tablib.Dataset(*self.data, headers=['func', 'method', 'access_type', 'level_up', 'level_down'])
        self.resource.import_data(dataset, dry_run=False, group=group.id)
        self.assertEqual(FunctionGroup.objects.filter(group=group).count(), 4)

    def test_export_function_groups(self):
        data = self.resource.export(queryset=FunctionGroup.objects.filter(group=self.employee_group))
        self.assertEqual(FunctionGroup.objects.filter(group=self.employee_group).count(), len(data))
        self.assertEqual(data.headers, ['func', 'method', 'access_type', 'level_up', 'level_down'])
