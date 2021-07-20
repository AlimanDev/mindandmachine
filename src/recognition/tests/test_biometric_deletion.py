from rest_framework.test import APITestCase
from unittest import mock
from datetime import date, timedelta

from src.celery.tasks import auto_delete_biometrics
from src.recognition.models import UserConnecter
from src.util.mixins.tests import TestsHelperMixin
from src.recognition.api.recognition import Recognition


class TestBiometricDeletion(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        UserConnecter.objects.create(user=cls.user1, partner_id=1)
        UserConnecter.objects.create(user=cls.user2, partner_id=2)
        UserConnecter.objects.create(user=cls.user3, partner_id=3)
        cls.dt = date.today()
        cls.employment1.dt_fired = cls.dt - timedelta(days=366 * 3)
        cls.employment1.save()
        cls.employment2.dt_fired = cls.dt - timedelta(days=364 * 3)
        cls.employment2.save()

    def setUp(self):
        self._set_authorization_token(self.user2.username)

    def test_delete_biometrics_after_3_years(self):
        with mock.patch.object(Recognition, 'delete_person') as delete_person:
            auto_delete_biometrics()
            delete_person.assert_called_once()
        self.assertEqual(UserConnecter.objects.count(), 2)
        self.assertIsNone(UserConnecter.objects.filter(user=self.user1).first())      
