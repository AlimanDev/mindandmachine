from rest_framework.test import APITestCase
from src.common.mixins.tests import TestsHelperMixin


class TestUserSubordination(TestsHelperMixin, APITestCase):
    """Testing of user subordination."""

    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def setUp(self) -> None:
        self.client.force_login(user=self.user1)

    def test_use_internal_exchange_in_network(self):
        """Testing query when use_internal_exchange is True."""
        self.network.use_internal_exchange = True
        self.network.save(update_fields=('use_internal_exchange',))
        response = self.client.get('/rest_api/auth/user/')
        self.assertIsNone(response.json().get('network_employee_ids'))

    def test_not_internal_exchange_in_network(self):
        self.network.use_internal_exchange = False
        self.network.save(update_fields=('use_internal_exchange',))
        response = self.client.get('/rest_api/auth/user/')
        data = response.json()
        self.assertIsNotNone(data.get('network_employee_ids'))
        self.assertEqual(data.get('network_employee_ids'), data.get('subordinate_employee_ids'))

    def test_user_subordination(self):
        self.assertEqual(len(self.user1.get_subordinates(network_id=self.network)), 8)
        self.assertEqual(len(self.user2.get_subordinates(network_id=self.network)), 0)
