from src.util.test import LocalTestCase
from django.conf import settings
import json
from src.db.models import User

class TestAutoSettings(LocalTestCase):

    def setUp(self):
        super().setUp()


    def test_get_status(self):
        self.auth()

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id=1')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        self.assertEqual(response.json['data']['status'], 'R')

    # Не дописан. Проблемы с cashier_ids.
    def test_set_selected_cashiers(self):
        self.auth()

        response = self.api_post('/api/timetable/auto_settings/set_selected_cashiers', {'cashier_ids': json.dumps([1,2]), 'shop_id': 1})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
        user = User.objects.filter(id__in=[1,2,3]).order_by('id')
        self.assertEqual(user[0].auto_timetable, True)
        self.assertEqual(user[1].auto_timetable, True)
        self.assertEqual(user[2].auto_timetable, False)

    # {'error_type': 'InternalError', 'error_message': 'Внутренняя ошибка сервера'}
    def test_set_timetable(self):
        self.auth()

        response = self.api_post('/api/timetable/auto_settings/set_timetable', {'key': settings.QOS_SET_TIMETABLE_KEY, 'data': json.dumps({})})
        print('set_timetable: ', response.json)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)