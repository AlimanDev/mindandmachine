from datetime import date, timedelta

from django.conf import settings
from rest_framework.test import APITestCase
from rest_framework import status

from src.apps.base.models import SAWHSettings, SAWHSettingsMapping
from src.apps.base.tests.factories import WorkerPositionFactory
from src.apps.timetable.models import WorkTypeName
from src.common.mixins.tests import TestsHelperMixin


class TestSAWHSettingsViewSet(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.worker_position = WorkerPositionFactory()
        cls.dt = date(year=2022, month=1, day=1)
    
    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_daily(self):
        url = '/rest_api/sawh_settings/daily/'
        query_params = {
            'dt_from': self.dt,
            'dt_to': self.dt.replace(month=3) - timedelta(1) #2 месяца
        }

        #Без SAWH
        res = self.client.get(url, query_params)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()), 59)
        self.assertDictEqual(res.json()[0], {
            'dt': self.dt.strftime(settings.QOS_DATE_FORMAT),
            'work_types': [],
            'worker_position': self.worker_position.id,
            'sawh': 0
        })

        #С SAWH
        sawhsettings = SAWHSettings.objects.create(
            work_hours_by_months={'m2': 200},
            network=self.network,
            name='Тест-SAWH',
        )
        sawhsettings.positions.add(self.worker_position)
        SAWHSettingsMapping.objects.create(
            sawh_settings=sawhsettings,
            year=self.dt.year,
            work_hours_by_months={'m1': 150},
        )
        work_type_name = WorkTypeName.objects.create(
            network=self.network,
            name='Тестовое имя работы',
        )
        self.worker_position.default_work_type_names.add(work_type_name)

        res = self.client.get(url, query_params)
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.json()), 59)
        self.assertDictEqual(res.json()[0], {
            'dt': (self.dt).strftime(settings.QOS_DATE_FORMAT),
            'work_types': [work_type_name.id],
            'worker_position': self.worker_position.id,
            'sawh': 4.84 # round(150 / 31, 2) 
        })
        self.assertDictEqual(res.json()[-1], {
            'dt': (self.dt.replace(month=3) - timedelta(1)).strftime(settings.QOS_DATE_FORMAT),
            'work_types': [work_type_name.id],
            'worker_position': self.worker_position.id,
            'sawh': 7.14 # round(200 / 28, 2) 
        })
        

        #Неправильный промежуток
        query_params['dt_to'] = self.dt - timedelta(1)
        res = self.client.get(url, query_params)
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)


