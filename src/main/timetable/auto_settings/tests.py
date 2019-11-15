import json
from unittest import skip

from src.db.models import User, Employment
from src.util.test import LocalTestCase


class TestAutoSettings(LocalTestCase):

    def setUp(self):
        super().setUp()

    def test_get_status(self):
        self.auth()

        response = self.api_get('/api/timetable/auto_settings/get_status?dt=01.06.2019&shop_id={}'.format(
            self.shop.id
        ))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
        self.assertEqual(response.json()['data']['status'], 'R')

    def test_set_selected_cashiers(self):
        self.auth()

        employment_cnt = Employment.objects.filter(
            shop=self.shop,
        ).count()

        ids=[self.user2.id, self.user3.id]
        response = self.api_post('/api/timetable/auto_settings/set_selected_cashiers',
                                 {'worker_ids': json.dumps(ids), 'shop_id': self.shop.id})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)

        employments = Employment.objects.filter(
            shop=self.shop,
            user_id__in=ids,
            auto_timetable=True
        )
        self.assertEqual(employments.count(), 2)

        employments = Employment.objects.filter(
            shop=self.shop,
            auto_timetable=False
        )
        self.assertEqual(employments.count(), employment_cnt - 2)

    # {'error_type': 'InternalError', 'error_message': 'Внутренняя ошибка сервера'} // no timetable_id
    @skip("set timetable 500")
    def test_set_timetable(self):
        self.auth()

        response = self.api_post('/api/timetable/auto_settings/set_timetable', {'data': json.dumps({})})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['code'], 200)
