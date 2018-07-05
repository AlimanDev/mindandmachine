import json
from django.test import TestCase
from src.db.models import User


class LocalTestCase(TestCase):
    USER_USERNAME = "u_1_1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user(self.USER_USERNAME, self.USER_EMAIL, self.USER_PASSWORD, id=11)

    def auth(self):
        self.client.post(
            '/api/auth/signin',
            {
                'username': self.USER_USERNAME,
                'password': self.USER_PASSWORD
            }
        )

    def api_get(self, *args, **kwargs):
        response = self.client.get(*args, **kwargs)
        response.json = json.loads(response.content.decode('utf-8'))
        return response

    def api_post(self, *args, **kwargs):
        response = self.client.post(*args, **kwargs)
        response.json = json.loads(response.content.decode('utf-8'))
        return response
