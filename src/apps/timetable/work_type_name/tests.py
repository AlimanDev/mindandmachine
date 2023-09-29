from rest_framework import status
from rest_framework.test import APITestCase

from src.apps.forecast.models import OperationType, OperationTypeName
from src.apps.timetable.models import WorkTypeName, WorkType
from src.common.mixins.tests import TestsHelperMixin


class TestWorkTypeName(APITestCase, TestsHelperMixin):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def setUpTestData(cls):
        cls.url = '/rest_api/work_type_name/'

        cls.create_departments_and_users()
        cls.work_type_name1 = WorkTypeName.objects.create(
            name='Кассы',
            network=cls.network,
        )
        cls.wt = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        cls.work_type_name2 = WorkTypeName.objects.create(
            name='Тип_кассы_2',
            network=cls.network,
        )
        cls.wt2 = WorkType.objects.create(shop=cls.shop2, work_type_name=cls.work_type_name2)
        cls.work_type_name3 = WorkTypeName.objects.create(
            name='Тип_кассы_3',
            network=cls.network,
        )
        cls.work_type_name4 = WorkTypeName.objects.create(
            name='тип_кассы_4',
            network=cls.network,
        )

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 4)

    def test_get(self):
        response = self.client.get(f'{self.url}{self.work_type_name1.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {'name': 'Кассы', 'code': None}
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
        self.assertIsNotNone(OperationTypeName.objects.filter(work_type_name_id=data['id']).first())

    def test_update(self):
        data = {
            'name': 'Склад',
            'code': '21',
        }
        response = self.client.put(f'{self.url}{self.work_type_name1.id}/', data, format='json')
        work_type_name = response.json()
        data['id'] = self.work_type_name1.id
        self.assertEqual(work_type_name, data)
        self.assertIsNotNone(OperationTypeName.objects.filter(work_type_name_id=data['id']).first())

    def test_update_code(self):
        data = {
            'code': '21',
        }
        response = self.client.put(f'{self.url}{self.work_type_name1.id}/', data, format='json')
        work_type_name = response.json()
        data['id'] = self.work_type_name1.id
        data['name'] = self.work_type_name1.name
        self.assertEqual(work_type_name, data)

    def test_update_name(self):
        data = {
            'name': 'Склад',
        }
        response = self.client.put(f'{self.url}{self.work_type_name1.id}/', data, format='json')
        work_type_name = response.json()
        data['id'] = self.work_type_name1.id
        data['code'] = self.work_type_name1.code
        self.assertEqual(work_type_name, data)

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.work_type_name1.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertIsNotNone(WorkTypeName.objects.get(id=self.work_type_name1.id).dttm_deleted)
        self.assertEqual(WorkType.objects.filter(dttm_deleted__isnull=False).count(), 1)

    def test_get_worktype_by_shops(self):
        response = self.client.get(self.url, data={'shop_id__in': f'{self.shop2.id}'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        resp_data = response.json()
        self.assertEqual(len(resp_data), 1)

        self.assertEqual(resp_data[0]['id'], self.work_type_name2.id)

    def test_work_type_name_create(self):
        OperationType.objects.all().delete()
        WorkType.objects.all().delete()
        # with name only
        wtn = WorkTypeName.objects.create(
            name='WorkTypeName',
            network=self.network,
        )
        otn = OperationTypeName.objects.filter(work_type_name_id=wtn.id).first()
        self.assertIsNotNone(otn)
        self.assertEqual(otn.name, wtn.name)

        OperationTypeName.objects.all().delete()
        WorkTypeName.objects.all().delete()

        otn = OperationTypeName.objects.create(
            name='WorkTypeName',
            network=self.network,
        )
        wtn = WorkTypeName.objects.create(
            name='WorkTypeName',
            network=self.network,
        )
        otn.refresh_from_db()
        self.assertEqual(otn.work_type_name_id, wtn.id)

        OperationTypeName.objects.all().delete()
        WorkTypeName.objects.all().delete()

        # with code
        otn = OperationTypeName.objects.create(
            name='OperationTypeName',
            code='work_type',
            network=self.network,
        )
        wtn = WorkTypeName.objects.create(
            name='WorkTypeName',
            code='work_type',
            network=self.network,
        )
        otn.refresh_from_db()
        self.assertEqual(otn.work_type_name_id, wtn.id)
        self.assertEqual(otn.name, wtn.name)

        otn.name = 'Other name'
        otn.save()
        wtn.name = 'Other work type name'
        wtn.save()
        otn.refresh_from_db()
        self.assertEqual(otn.name, wtn.name)

        wtn.delete()
        wtn.refresh_from_db()
        otn.refresh_from_db()
        self.assertIsNotNone(wtn.dttm_deleted)
        self.assertIsNotNone(otn.dttm_deleted)
