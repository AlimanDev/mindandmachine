from rest_framework.test import APITestCase
from src.util.mixins.tests import TestsHelperMixin


class TestRegionAPI(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def test_get_regions(self):
        self.client.force_authenticate(user=self.user1)
        response = self.client.get('/rest_api/region/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)