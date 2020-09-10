from django.test import TestCase

from src.base.models import (
    WorkerPosition,
    Network,
)
from src.timetable.models import (
    WorkTypeName,
)
from src.util.utils import set_position_default_work_type_names


class TestSetPositionDefaultWorkTypeNames(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = Network.objects.first()
        cls.worker_position = WorkerPosition.objects.create(name='Врач-терапевт', network=cls.network)
        cls.worker_position2 = WorkerPosition.objects.create(name='Директор', network=cls.network)
        cls.worker_position3 = WorkerPosition.objects.create(name='Продавец-кассир', network=cls.network)
        cls.worker_position4 = WorkerPosition.objects.create(name='ЗДМ', network=cls.network)

        WorkTypeName.objects.bulk_create(
            [
                WorkTypeName(
                    name=name,
                    code=code,
                    network=cls.network,
                )
                for name, code in [('Врач', '0001'), ('Продавец', '0002'), ('Еще', '0003')]
            ]
        )

    def test_set_position_default_work_type_names_func(self):
        mapping = {
            r'(.*)?врач(.*)?': ('0001',),
            r'(.*)?кассир(.*)?': ('0002', '0003'),
        }
        set_position_default_work_type_names(mapping)
        self.assertEqual(self.worker_position.default_work_type_names.count(), 1)
        self.assertEqual(self.worker_position2.default_work_type_names.count(), 0)
        self.assertEqual(self.worker_position3.default_work_type_names.count(), 2)
        self.assertEqual(self.worker_position4.default_work_type_names.count(), 0)
