from rest_framework.test import APITestCase

from src.base.tests.factories import NetworkFactory, ShopFactory, UserFactory, GroupFactory, EmploymentFactory, EmployeeFactory
from src.recognition.models import TickPoint
from src.util.mixins.tests import TestsHelperMixin
from .factories import TickPointFactory


class TestTickPointViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.user = UserFactory(network=cls.network)
        cls.employee = EmployeeFactory(user=cls.user)
        cls.shop = ShopFactory(network=cls.network)
        cls.group = GroupFactory(network=cls.network)
        cls.employment = EmploymentFactory(employee=cls.employee, shop=cls.shop, function_group=cls.group)
        cls.tick_point = TickPointFactory(shop=cls.shop)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_tick_point(self):
        self.add_group_perm(self.group, 'TickPoint', 'GET')

        resp = self.client.get(self.get_url('TickPoint-list'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)

    def test_list_tick_point_filtered(self):
        self.add_group_perm(self.group, 'TickPoint', 'GET')
        self.shop2 = ShopFactory(network=self.network)
        self.shop3 = ShopFactory(network=self.network)
        TickPointFactory(shop=self.shop2)
        TickPointFactory(shop=self.shop3)

        resp = self.client.get(self.get_url('TickPoint-list'))
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 3)
        resp = self.client.get(self.get_url('TickPoint-list') + f'?shop_id={self.shop.id}')
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)
        resp = self.client.get(self.get_url('TickPoint-list') + f'?shop_id__in={self.shop.id},{self.shop2.id}')
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 2)


    def test_get_tick_point(self):
        self.add_group_perm(self.group, 'TickPoint', 'GET')

        resp = self.client.get(self.get_url('TickPoint-detail', pk=self.tick_point.pk))
        self.assertEqual(resp.status_code, 200)

    def test_create_and_update_tick_point(self):
        # create
        self.add_group_perm(self.group, 'TickPoint', 'POST')
        tick_point_data = {
            'shop_id': self.shop.id,
            'name': 'Точка отметок',
            'code': 'tick_point',
        }
        resp = self.client.post(
            self.get_url('TickPoint-list'), data=self.dump_data(tick_point_data), content_type='application/json')
        self.assertEqual(resp.status_code, 201)
        resp_data = resp.json()
        created_tick_point = TickPoint.objects.get(id=resp_data['id'])
        self.assertEqual(created_tick_point.network_id, self.network.id)
        self.assertEqual(resp_data['key'], str(created_tick_point.key))
        self.assertEqual('Точка отметок', created_tick_point.name)
        self.assertEqual('tick_point', created_tick_point.code)
        self.assertEqual(self.shop.id, created_tick_point.shop_id)

        # update
        tick_point_data['name'] = 'Точка отметок2'
        tick_point_data['code'] = 'tick_point2'
        self.add_group_perm(self.group, 'TickPoint', 'PUT')
        resp = self.client.put(self.get_url('TickPoint-detail', pk=created_tick_point.pk), data=tick_point_data)
        self.assertEqual(resp.status_code, 200)
        created_tick_point.refresh_from_db()
        self.assertEqual('Точка отметок2', created_tick_point.name)
        self.assertEqual('tick_point2', created_tick_point.code)

    def test_delete_tick_point(self):
        self.add_group_perm(self.group, 'TickPoint', 'DELETE')
        resp = self.client.delete(self.get_url('TickPoint-detail', pk=self.tick_point.pk))
        self.assertEqual(resp.status_code, 204)
        self.assertTrue(TickPoint.objects.filter(id=self.tick_point.id).exists())
        self.tick_point.refresh_from_db()
        self.assertIsNotNone(self.tick_point.dttm_deleted)
