from django.test import TestCase
from rest_framework.test import APITestCase

from src.base.models import WorkerPosition
from src.base.tests.factories import GroupFactory, NetworkFactory, BreakFactory
from src.timetable.models import WorkTypeName
from src.timetable.tests.factories import WorkTypeNameFactory
from src.util.mixins.tests import TestsHelperMixin
import json


class TestWorkerPositionAPI(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.network.worker_position_default_values = json.dumps(
           {
                r'(.*)?Врач(.*)?': {
                    'hours_in_a_week': 39,
                    'group_code': 'worker',
                    'breaks_code': None
                },
            }
        )
        cls.network.save()
        WorkerPosition.objects.bulk_create(
            [
                WorkerPosition(
                    name=name,
                    code=code,
                    network=cls.network,
                )
                for name, code in [
                ('Директор магазина', 'director'),
                ('Продавец', 'seller'),
                ('Продавец-кассир', 'seller2'),
                ('ЗДМ', 'director2'),
            ]
            ]
        )
        cls.worker_position = WorkerPosition.objects.last()
        cls.worker_positions_count = 4
        cls.wt_name = WorkTypeName.objects.create(name='test_name', code='test_code')
        cls.wt_name2 = WorkTypeName.objects.create(name='test_name2', code='test_code2')

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_list(self):
        resp = self.client.get(self.get_url('WorkerPosition-list'))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), self.worker_positions_count)
        self.assertEqual(resp.json()[0]['name'], 'Директор магазина')
        self.assertEqual(resp.json()[1]['name'], 'ЗДМ')

    def test_create(self):
        data = {
            'name': 'Врач',
            'network_id': self.network.id,
            'code': 'doctor',
        }

        resp = self.client.post(
            self.get_url('WorkerPosition-list'), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(
            WorkerPosition.objects.filter(dttm_deleted__isnull=True).count(), self.worker_positions_count + 1)

        wp = WorkerPosition.objects.get(id=resp.json()['id'])
        self.assertEqual(wp.hours_in_a_week, 39)
        self.assertEqual(wp.group_id, self.employee_group.id)
        self.assertEqual(wp.breaks_id, None)

        # проверка, что нельзя создать еще одну позицию с таким же кодом
        resp = self.client.post(
            self.get_url('WorkerPosition-list'), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()['code'], ['Это поле должно быть уникально.'])

    def test_create_and_update_with_put_by_code(self):
        data = {
            'name': 'Врач',
            'network_id': self.network.id,
            'code': 'doctor',
            'by_code': True,
        }

        resp = self.client.put(
            self.get_url('WorkerPosition-detail', pk=data['code']), data=self.dump_data(data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        wp = WorkerPosition.objects.get(id=resp.json()['id'])
        data['name'] = 'Доктор'
        resp = self.client.put(
            self.get_url('WorkerPosition-detail', pk=data['code']), data=self.dump_data(data),
            content_type='application/json')
        self.assertEqual(resp.status_code, 200)
        wp.refresh_from_db()
        self.assertEqual(wp.name, data['name'])

    def test_retrieve(self):
        resp = self.client.get(self.get_url('WorkerPosition-detail', pk=self.worker_position.id))
        self.assertEqual(resp.status_code, 200)

    def test_put(self):
        put_data = {
            'name': 'test_name',
            'network_id': self.network.id,
            'code': 'test_code',
        }
        resp = self.client.put(
            path=self.get_url('WorkerPosition-detail', pk=self.worker_position.id),
            data=self.dump_data(put_data),
            content_type='application/json',
        )
        self.assertEqual(resp.status_code, 200)

    def test_delete(self):
        resp = self.client.delete(path=self.get_url('WorkerPosition-detail', pk=self.worker_position.id))
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(
            WorkerPosition.objects.filter(dttm_deleted__isnull=True).count(), self.worker_positions_count - 1)


class TestSetWorkerPositionDefaultsModel(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.network.worker_position_default_values = json.dumps(
           {
                r'(.*)?врач|травматолог|ортопед(.*)?': {
                    'default_work_type_names_codes': ('doctor',),
                    'hours_in_a_week': 39,
                    'group_code': 'worker',
                    'breaks_code': 'doctor'
                },
                r'(.*)?продавец|кассир|менеджер|консультант(.*)?': {
                    'default_work_type_names_codes': ('consult',),
                    'hours_in_a_week': 40,
                    'group_code': 'worker',
                    'breaks_code': 'consult'
                },
                r'(.*)?директор|управляющий(.*)?': {
                    'default_work_type_names_codes': ('consult',),
                    'hours_in_a_week': 40,
                    'group_code': 'director',
                    'breaks_code': 'director'
                },
                r'(.*)?кладовщик|уборщик|курьер(.*)?': {
                    'default_work_type_names_codes': ('other',),
                    'hours_in_a_week': 40,
                    'group_code': 'worker',
                    'breaks_code': None
                },
            }
        )
        cls.network.save()
        cls.group_director = GroupFactory(name='Директор', code='director')
        cls.group_worker = GroupFactory(name='Сотрудник', code='worker')
        cls.work_type_name_consult = WorkTypeNameFactory(
            name='Продавец-кассир',
            code='consult',
        )
        cls.work_type_name_doctor = WorkTypeNameFactory(
            name='Врач',
            code='doctor',
        )
        cls.work_type_name_other = WorkTypeNameFactory(
            name='Кладовщик, курьер',
            code='other',
        )
        cls.breaks_consult = BreakFactory(name='Продавец-кассир', code='consult')
        cls.breaks_doctor = BreakFactory(name='Врач', code='doctor')
        cls.breaks_director = BreakFactory(name='Директор', code='director')

    def test_defaults_was_set_on_position_creation(self):
        wp = WorkerPosition(network=self.network, name='Продавец-кассир Город')
        wp.save()
        self.assertEqual(wp.group_id, self.group_worker.id)
        self.assertEqual(wp.breaks_id, self.breaks_consult.id)
        self.assertEqual(wp.hours_in_a_week, 40)
        self.assertListEqual(
            [self.work_type_name_consult.id],
            list(wp.default_work_type_names.values_list('id', flat=True))
        )

        wp2 = WorkerPosition(network=self.network, name='Директор Город')
        wp2.save()
        self.assertEqual(wp2.group_id, self.group_director.id)
        self.assertEqual(wp2.breaks_id, self.breaks_director.id)
        self.assertEqual(wp2.hours_in_a_week, 40)
        self.assertListEqual(
            [self.work_type_name_consult.id],
            list(wp2.default_work_type_names.values_list('id', flat=True))
        )

        wp3 = WorkerPosition(network=self.network, name='Эксперт по ортопедическим изделиям Город')
        wp3.save()
        self.assertEqual(wp3.group_id, self.group_worker.id)
        self.assertEqual(wp3.breaks_id, self.breaks_doctor.id)
        self.assertEqual(wp3.hours_in_a_week, 39)
        self.assertListEqual(
            [self.work_type_name_doctor.id],
            list(wp3.default_work_type_names.values_list('id', flat=True))
        )

        wp4 = WorkerPosition(network=self.network, name='Курьер Город')
        wp4.save()
        self.assertEqual(wp4.group_id, self.group_worker.id)
        self.assertEqual(wp4.breaks_id, None)
        self.assertEqual(wp4.hours_in_a_week, 40)
        self.assertListEqual(
            [self.work_type_name_other.id],
            list(wp4.default_work_type_names.values_list('id', flat=True))
        )
