from datetime import timedelta

from django.db.models import Q
from django.test import TestCase

from src.timetable.exceptions import DtMaxHoursRestrictionViolated
from src.timetable.models import (
    WorkerDay,
    Restriction,
)
from src.timetable.tests.factories import WorkerDayFactory
from src.util.mixins.tests import TestsHelperMixin


class TestCheckRestrictions(TestsHelperMixin, TestCase):
    def test_check_exception_raised_when_restriction_exists(self):
        wd = WorkerDayFactory(
            is_fact=False,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        restriction = Restriction.objects.create(
            is_vacancy=None,
            worker_day_type_id=WorkerDay.TYPE_WORKDAY,
            dt_max_hours=timedelta(hours=5),
            restriction_type=Restriction.RESTRICTION_TYPE_DT_MAX_HOURS,
        )
        expected_msg = 'Операция не может быть выполнена. ' \
                       'Нарушены ограничения по максимальному количеству часов'
        with self.assertRaisesMessage(DtMaxHoursRestrictionViolated, expected_msg):
            Restriction.check_restrictions(employee_days_q=Q(id=wd.id), is_fact=False)

        Restriction.objects.all().delete()
        restriction.dt_max_hours = timedelta(hours=12)
        restriction.save()
        restrictions = Restriction.check_restrictions(employee_days_q=Q(id=wd.id), is_fact=False)
        self.assertEqual(len(restrictions), 1)
        self.assertListEqual(list(restrictions[0]['dt_max_hours_restrictions']), [])
