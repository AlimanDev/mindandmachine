from datetime import timedelta

from django.test import TestCase

from src.apps.timetable.models import (
    WorkerDay,
    WorkerDayType,
)
from src.apps.timetable.tests.factories import WorkerDayFactory
from src.common.mixins.tests import TestsHelperMixin


class TesCalcWorkHours(TestsHelperMixin, TestCase):
    maxDiff = None

    def test_breaks_subtracted_when_wd_type_settings_is_enabled(self):
        wd = WorkerDayFactory(
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        self.assertEqual(wd.work_hours, timedelta(seconds=31500))

    def test_breaks_not_subtracted_when_wd_type_settings_is_enabled(self):
        WorkerDayType.objects.filter(code=WorkerDay.TYPE_WORKDAY).update(subtract_breaks=False)
        wd = WorkerDayFactory(
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        self.assertEqual(wd.work_hours, timedelta(seconds=36000))
