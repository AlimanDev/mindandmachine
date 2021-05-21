from datetime import datetime, date, time
from dateutil.relativedelta import relativedelta

from rest_framework import status
from rest_framework.test import APITestCase

from src.util.test import create_departments_and_users

from src.timetable.models import VacancyBlackList, WorkerDay, WorkerDayCashboxDetails, WorkType, WorkTypeName
from src.util.models_converter import Converter
from src.timetable.vacancy.utils import confirm_vacancy



class TestVacancyBlackList(APITestCase):
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()

        self.url = '/rest_api/vacancy_black_list/'

        create_departments_and_users(self)
        
        
        self.black_list = VacancyBlackList.objects.create(
            shop_id=self.shop.id,
            symbol='1234',
        )

        self.black_list2 = VacancyBlackList.objects.create(
            shop_id=self.shop.id,
            symbol='4321',
        )

        self.client.force_authenticate(user=self.user1)

    def test_get_list(self):
        response = self.client.get(f'{self.url}?shop_id={self.shop.id}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.json()), 2)

    
    def test_get(self):
        response = self.client.get(f'{self.url}{self.black_list.id}/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = {
            'id': self.black_list.id, 
            'shop_id': self.shop.id, 
            'symbol': '1234',
        }
        
        self.assertEqual(response.json(), data)


    def test_create(self):
        data = {
            'shop_id': self.shop2.id,
            'symbol': '12345',
        }
        response = self.client.post(self.url, data, format='json')
        black_list = response.json()
        data['id'] = black_list['id']
        self.assertEqual(black_list, data)


    def test_update(self):
        data = {
            'shop_id': self.shop2.id,
            'symbol': '12345',
        }
        response = self.client.put(f'{self.url}{self.black_list.id}/', data, format='json')
        black_list = response.json()
        data['id'] = self.black_list.id
        self.assertEqual(black_list, data)
    

    def test_delete(self):
        response = self.client.delete(f'{self.url}{self.black_list.id}/')
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)


    def test_cant_apply_vacancy(self):
        self.user1.black_list_symbol = '1234'
        self.user1.save()
        self.work_type_name = WorkTypeName.objects.create(
            name='Кассы',
            code='',
        )

        self.work_type1 = WorkType.objects.create(
            shop=self.shop,
            work_type_name=self.work_type_name,
        )
        dt_now = date.today()
        WorkerDay.objects.create(
            type=WorkerDay.TYPE_HOLIDAY,
            dt=dt_now,
            shop=self.work_type1.shop,
            employment=self.employment1,
        )
        wd = WorkerDay.objects.create(
            dttm_work_start=datetime.combine(dt_now, time(10)),
            dttm_work_end=datetime.combine(dt_now, time(20)),
            type=WorkerDay.TYPE_WORKDAY,
            is_vacancy=True,
            is_approved=True,
            dt=dt_now,
            shop=self.work_type1.shop,
        )
        WorkerDayCashboxDetails.objects.create(
            worker_day=wd,
            work_type=self.work_type1,
        )

        result = confirm_vacancy(wd.id, self.user1)

        self.assertEqual(
            {'status_code': 400, 'text': 'Вы не можете выйти на эту смену.'},
            result,
        )
