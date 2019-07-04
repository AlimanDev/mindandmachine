from src.util.test import LocalTestCase


class TestUpload(LocalTestCase):

    def setUp(self):
        super().setUp()

    # Сервер для обработки алгоритма недоступен.
    def test_upload_demand(self):
        self.auth()

        file = open('src/main/upload/test_data/test_demand_upload.xlsx', 'rb')
        response = self.api_post('/api/upload/upload_demand', {'shop_id': 1, 'file': file})
        file.close()
        print('test_upload_demand: ', response.json)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)

    def test_upload_timetable(self):
        self.auth()

        file = open('src/main/upload/test_data/test_timetable_upload.xlsx', 'rb')
        response = self.api_post('/api/upload/upload_timetable', {'shop_id': 1, 'file': file})
        file.close()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['code'], 200)
