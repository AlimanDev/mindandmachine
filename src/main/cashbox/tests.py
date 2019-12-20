from src.util.test import LocalTestCase, datetime
from src.timetable.models import WorkType, Cashbox


class TestCashbox(LocalTestCase):

    def setUp(self):
        super().setUp()
        WorkType.objects.update(dttm_added=datetime.datetime(2018, 1, 1, 0, 0, 0))


    def test_get_types(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_types?shop_id={}'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        # Поступает больше данных, чем мы проверяем.
        # self.assertEqual(response.json()['data'], [
        #     {'id': 2, 'dttm_added': '00:00:00 01.01.2018', 'dttm_deleted': None, 'shop': 1, 'name': 'тип_кассы_2',
        #      ''
        #      'speed_coef': 1.0},
        #     {'id': 1, 'dttm_added': '00:00:00 01.01.2018', 'dttm_deleted': None, 'shop': 1, 'name': 'тип_кассы_1',
        #      'speed_coef': 1.0}
        # ])

    def test_get_cashboxes(self):
        self.auth()
        response = self.api_get('/api/cashbox/get_cashboxes?shop_id={}&work_type_ids=[]'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(len(response.json()['data']['work_types']), 2)
        self.assertEqual(len(response.json()['data']['cashboxes']), 2)

    def test_create_cashbox(self):
        self.auth()
        response = self.api_post('/api/cashbox/create_cashbox', {
            'work_type_id': 1,
            'number': 1
        })

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()['code'], 400)
        self.assertEqual(response.json()['data']['error_type'], 'AlreadyExist')

    def test_delete_cashbox(self):
        '''
        Note: Внутри данной функции используется дополнительная функция send_notification
        '''
        self.auth()
        data = {
            'shop_id': self.shop.id,
            'work_type_id': self.work_type1.id,
            'number': self.cashbox1.number,
            'bio': 'Cashbox crashed',
        }
        response = self.api_post(
            '/api/cashbox/delete_cashbox',
            data
        )
        res_json = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(res_json['code'], 200)
        self.assertEqual(res_json['data']['id'], 1)
        self.assertEqual(res_json['data']['dttm_added'], "08:30:00 01.01.2018")
        self.assertEqual(res_json['data']['type'], 1)
        self.assertEqual(res_json['data']['number'], 1)
        self.assertEqual(res_json['data']['bio'], 'Cashbox crashed')

    def test_update_cashbox(self):
        self.auth()
        Cashbox.objects.filter(id=1).update(id=200)
        data = {
            'from_work_type_id': self.work_type2.id,
            'to_work_type_id': self.work_type1.id,
            'number': self.cashbox2.number,
        }
        response = self.api_post(
            '/api/cashbox/update_cashbox',
            data
        )
        res_json = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(res_json['code'], 200)
        self.assertEqual(res_json['data']['id'], 1)
        self.assertEqual(res_json['data']['type'], 1)
        self.assertEqual(res_json['data']['number'], '2')
        self.assertEqual(res_json['data']['bio'], '')
    
    def test_create_work_type(self):
        '''
        Note: Внутри данной функции используется дополнительная функция send_notification
        '''
        self.auth()
        WorkType.objects.filter(id=1).update(id=200)
        data = {
            'shop_id': self.shop.id,
            'name': 'Уборка'
        }
        response = self.api_post(
            '/api/cashbox/create_work_type',
            data
        )
        res_json = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(res_json['code'], 200)
        self.assertEqual(res_json['data']['id'], 1)
        self.assertEqual(res_json['data']['dttm_deleted'], None)
        self.assertEqual(res_json['data']['shop'], 13)
        self.assertEqual(res_json['data']['priority'], 100)
        self.assertEqual(res_json['data']['name'], 'Уборка')
        self.assertEqual(res_json['data']['prob'], 1.0)
        self.assertEqual(res_json['data']['prior_weight'], 1.0)
        self.assertEqual(res_json['data']['min_workers_amount'], 0)
        self.assertEqual(res_json['data']['max_workers_amount'], 20)
        
    def test_delete_work_type(self):
        '''
        Note: Внутри данной функции используется дополнительная функция send_notification
        '''
        self.auth()
        data = {
            'work_type_id' : self.work_type1.id,
        }
        response = self.api_post(
            '/api/cashbox/delete_work_type',
            data
        )
        res_json = response.json()
        self.assertEqual(response.status_code, 500)
        self.assertEqual(res_json['code'], 500)
        self.assertEqual(res_json['data']['error_type'], 'InternalError')
        self.assertEqual(res_json['data']['error_message'], 'there are cashboxes on this type')
        Cashbox.objects.filter(type_id=self.work_type1.id).update(type=self.work_type2)
        response = self.api_post(
            '/api/cashbox/delete_work_type',
            data
        )
        res_json = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(res_json['code'], 200)
        self.assertEqual(res_json['data']['id'], 1)
        self.assertEqual(res_json['data']['dttm_added'], '00:00:00 01.01.2018')
        self.assertEqual(res_json['data']['shop'], 13)
        self.assertEqual(res_json['data']['priority'], 100)
        self.assertEqual(res_json['data']['name'], 'Кассы')
        self.assertEqual(res_json['data']['prob'], 1.0)
        self.assertEqual(res_json['data']['prior_weight'], 1.0)
        self.assertEqual(res_json['data']['min_workers_amount'], 0)
        self.assertEqual(res_json['data']['max_workers_amount'], 20)
