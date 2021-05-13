from rest_framework.test import APITestCase
from src.base.models import Group, FunctionGroup
from src.base.admin import GroupAdmin
from src.util.mixins.tests import TestsHelperMixin
from django.urls import reverse
from django.contrib.admin.sites import AdminSite


class MockRequest:
    POST = {
        '_saveasnew': 'Save as new',
    }
    def __init__(self, url):
        self.path = url


class TestBreakValidation(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()

    def setUp(self):
        self.client.force_authenticate(user=self.user1)

    def test_create_group_copy(self):
        group = self.admin_group
        url = reverse('admin:base_group_change', args=(group.id,))
        group_admin = GroupAdmin(model=Group, admin_site=AdminSite())
        new_group = group
        new_group.id = None
        name = group.name + '2'
        code = group.code + '2'
        new_group.name = name
        new_group.code = code
        group_admin.save_model(
            obj=new_group, 
            request=MockRequest(url=url),
            form=None, 
            change=None,
        )
        self.assertIsNotNone(new_group.id)
        self.assertEqual(new_group.name, name)
        self.assertEqual(new_group.code, code)
        self.assertEqual(FunctionGroup.objects.filter(group=new_group).count(), FunctionGroup.objects.filter(group=group).count())
