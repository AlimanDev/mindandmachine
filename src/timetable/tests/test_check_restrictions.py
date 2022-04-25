from datetime import timedelta

from django.db.models import Q
from django.test import TestCase

from src.base.models import (
    SAWHSettings,
)
from src.base.tests.factories import (
    WorkerPositionFactory,
)
from src.timetable.exceptions import (
    DtMaxHoursRestrictionViolated,
    SawhSettingsIsNotSetRestrictionViolated,
)
from src.timetable.models import (
    WorkerDay,
    Restriction,
)
from src.timetable.tests.factories import (
    WorkerDayFactory,
)
from src.util.mixins.tests import TestsHelperMixin


class TestCheckRestrictions(TestsHelperMixin, TestCase):
    def test_check_exception_raised_when_dt_max_hours_restriction_exists(self):
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

    def test_check_exception_raised_when_sawh_settings_is_not_set_restriction_exists(self):
        wd = WorkerDayFactory(
            employment__position=WorkerPositionFactory(),
            is_fact=False,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
        )
        Restriction.objects.create(
            is_vacancy=None,
            worker_day_type_id=WorkerDay.TYPE_WORKDAY,
            dt_max_hours=timedelta(hours=5),
            restriction_type=Restriction.RESTRICTION_TYPE_SAWH_SETTINGS_IS_NOT_SET,
        )
        expected_msg = 'Операция не может быть выполнена. ' \
                       'Не настроена норма часов у сотрудников'
        with self.assertRaisesMessage(SawhSettingsIsNotSetRestrictionViolated, expected_msg):
            Restriction.check_restrictions(employee_days_q=Q(id=wd.id), is_fact=False)

        sawh_settings = SAWHSettings.objects.create(
            network=wd.shop.network,
            work_hours_by_months={},
            type=SAWHSettings.FIXED_HOURS,
        )
        wd.employment.sawh_settings = sawh_settings
        wd.employment.save()
        restrictions = Restriction.check_restrictions(employee_days_q=Q(id=wd.id), is_fact=False)
        self.assertEqual(len(restrictions), 1)
        self.assertListEqual(list(restrictions[0]['dt_max_hours_restrictions']), [])

        wd.employment.sawh_settings = None
        wd.employment.position.sawh_settings = sawh_settings
        wd.employment.save()
        wd.employment.position.save()
        restrictions = Restriction.check_restrictions(employee_days_q=Q(id=wd.id), is_fact=False)
        self.assertEqual(len(restrictions), 1)
        self.assertListEqual(list(restrictions[0]['dt_max_hours_restrictions']), [])
