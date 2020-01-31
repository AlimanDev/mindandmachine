from datetime import datetime
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import WorkTypeName, WorkType
from src.base.models import FunctionGroup


class TestWorkTypeName(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/work_type_name/'

        create_departments_and_users(self)
        self.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            code='',
        )
        WorkType.objects.create(shop=self.shop, work_type_name=self.work_type_name1)
        self.work_type_name2 = WorkTypeName.objects.create(
            name='Тип_кассы_2',
            code='',
        )
        self.work_type_name3 = WorkTypeName.objects.create(
            name='Тип_кассы_3',
            code='',
        )
        self.work_type_name4 = WorkTypeName.objects.create(
            name='тип_кассы_4',
            code='',
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='POST',
            func='WorkTypeName',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='PUT',
            func='WorkTypeName',
            level_up=1,
            level_down=99,
        )
        FunctionGroup.objects.create(
            group=self.admin_group,
            method='DELETE',
            func='WorkTypeName',
            level_up=1,
            level_down=99,
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 4)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.work_type_name1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {'name': 'Кассы', 'code': ''}
        data['id'] = response.json()['id']
        self.assertEqual(response.json(), data)

    def test_create(self):
        data = {
            'name': 'Отдел электроники',
            'code': '23',
        }
        response = self.client.post(self.url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        work_type_name = response.json()
        data['id'] = work_type_name['id']
        self.assertEqual(work_type_name, data)

    def test_update(self):
        data = {
            'name': 'Склад',
            'code': '21',
        }
        response = self.client.put(f'{self.url}{self.work_type_name1.id}/', data, format='json')
        work_type_name = response.json()
        data['id'] = self.work_type_name1.id
        self.assertEqual(work_type_name, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.work_type_name1.id}/')
        work_type_name = response.json()
        self.assertEqual(work_type_name['id'], self.work_type_name1.id)
        self.assertIsNotNone(WorkTypeName.objects.get(id=self.work_type_name1.id).dttm_deleted)
        self.assertEqual(WorkType.objects.filter(dttm_deleted__isnull=False).count(), 1)


    