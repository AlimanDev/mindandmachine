from rest_framework.test import APITestCase

from src.base.tests.factories import NetworkFactory, ShopFactory, UserFactory, GroupFactory, EmploymentFactory
from src.recognition.models import TickPoint
from src.util.mixins.tests import TestsHelperMixin
from .factories import TickPointFactory


class TestTickPointViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory()
        cls.user = UserFactory(network=cls.network)
        cls.shop = ShopFactory(network=cls.network)
        cls.group = GroupFactory(network=cls.network)
        cls.employment = EmploymentFactory(network=cls.network, user=cls.user, shop=cls.shop, function_group=cls.group)
        cls.tick_point = TickPointFactory(shop=cls.shop)

    def setUp(self):
        self.client.force_authenticate(user=self.user)

    def test_list_tick_point(self):
        self.add_group_perm(self.group, 'TickPoint', 'GET')

        resp = self.client.get(self.get_url('TickPoint-list'))
        self.assertEqual(resp.status_code, 200)
        resp_data = resp.json()
        self.assertEqual(len(resp_data), 1)

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
