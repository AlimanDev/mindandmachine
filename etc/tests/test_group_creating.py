from django.test import TestCase

from etc.scripts.create_access_groups import update_group_functions
from src.apps.base.models import (
    Group,
    FunctionGroup,
    Network,
)


class TestCreateGroupFunctions(TestCase):
    @classmethod
    def setUpTestData(self):
        self.network = Network.objects.create(name='net')

    def test_create_funcs(self):
        update_group_functions(None, network=self.network, verbose=False)

        self.assertEqual(Group.objects.filter(network=self.network).count(), 5)
        self.assertEqual(FunctionGroup.objects.filter(group__network=self.network).count(), 1280)
