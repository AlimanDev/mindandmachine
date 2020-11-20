from django.test import TestCase

from src.base.models import Group
from src.timetable.models import GroupWorkerDayPermission
from src.util.mixins.tests import TestsHelperMixin
from src.util.wd_perms.utils import (
    AdminPreset, URSOrtekaPreset, DirectorOrtekaPreset, EmptyPreset, DirectorAndURSMtsPreset
)


class TestWdPermsPresets(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.group = Group.objects.create(name='Тест')

    def _test_wd_perm(self, preset_cls, expected_count):
        preset = preset_cls()
        preset.activate_preset(self.group)
        self.assertEqual(GroupWorkerDayPermission.objects.filter(group=self.group).count(), expected_count)

    def test_wd_perms(self):
        self._test_wd_perm(AdminPreset, 66)
        self._test_wd_perm(URSOrtekaPreset, 66)
        self._test_wd_perm(DirectorOrtekaPreset, 35)
        self._test_wd_perm(DirectorAndURSMtsPreset, 30)
        self._test_wd_perm(EmptyPreset, 0)
