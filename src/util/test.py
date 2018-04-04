import json

from django.test import TestCase as DjangoTestCase


class TestCase(DjangoTestCase):
    def set_up(self):
        pass

    def setUp(self):
        self.set_up()

    def do_get(self, path, expected_code=200, expected_error_type=None):
        response = self.client.get(path)
        return self.__process_response(response, expected_code, expected_error_type)

    def do_post(self, path, data=None, expected_code=200, expected_error_type=None):
        response = self.client.post(path, data)
        return self.__process_response(response, expected_code, expected_error_type)

    def __process_response(self, response, expected_code, expected_error_type):
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.content.decode('utf-8'))
        self.assertEqual(data['code'], expected_code)
        if expected_code != 200:
            self.assertEqual(data['data']['error_type'], expected_error_type)

        return data['data']
