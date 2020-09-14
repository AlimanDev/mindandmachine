import json

from django.urls import reverse

from src.util.test import create_departments_and_users


class TestsHelperMixin:
    USER_USERNAME = "user1"
    USER_EMAIL = "q@q.q"
    USER_PASSWORD = "4242"

    @classmethod
    def create_departments_and_users(cls):
        create_departments_and_users(cls)

    @staticmethod
    def get_url(view_name, **kwargs: dict):
        return reverse(view_name, kwargs=kwargs)

    def print_resp(self, resp):
        print(json.dumps(resp.json(), indent=4, ensure_ascii=False))

    @staticmethod
    def dump_data(data):
        return json.dumps(data)
