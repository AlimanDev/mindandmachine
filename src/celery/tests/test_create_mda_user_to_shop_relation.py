from datetime import time, datetime, timedelta
from unittest import mock

from django.db import transaction
from django.test import TestCase
from django.utils import timezone

from src.integration.mda.tasks import sync_mda_user_to_shop_relation
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkTypeName, WorkType
from src.util.mixins.tests import TestsHelperMixin


@mock.patch('src.integration.mda.tasks.requests.post')
class TestCreateMDAUserToShopRelation(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_now = timezone.now().date()
        cls.create_departments_and_users()
        cls.wd = WorkerDay.objects.create(
            employee=cls.employee2,
            employment=cls.employment2,
            dt=cls.dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=cls.shop2,
            dttm_work_start=datetime.combine(cls.dt_now, time(9, 0, 0)),
            dttm_work_end=datetime.combine(cls.dt_now, time(18, 0, 0)),
            is_vacancy=True,
            is_fact=False, is_approved=True,
        )
        cls.work_type_name1 = WorkTypeName.objects.create(name='Тест')
        cls.work_type1 = WorkType.objects.create(shop=cls.shop, work_type_name=cls.work_type_name1)
        WorkerDayCashboxDetails.objects.create(
            work_type=cls.work_type1,
            worker_day=cls.wd,
            work_part=1,
        )

    def test_create_mda_user_to_shop_rel_called_with_enabled_setting(self, _requests_post):
        with self.settings(MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE=True, CELERY_TASK_ALWAYS_EAGER=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                self.wd.save()

        _requests_post.assert_called_once()

    def test_create_mda_user_to_shop_rel_not_called_with_disabled_setting(self, _requests_post):
        with self.settings(MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE=False, CELERY_TASK_ALWAYS_EAGER=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                self.wd.save()

        _requests_post.assert_not_called()

    def test_create_mda_user_to_shop_rel_not_called_if_shop_employment_is_the_same(self, _requests_post):
        self.wd.shop = self.shop
        with self.settings(MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE=True, CELERY_TASK_ALWAYS_EAGER=True):
            with mock.patch.object(transaction, 'on_commit', lambda t: t()):
                self.wd.save()

        _requests_post.assert_not_called()

    def _test_sync_task(self, _requests_post, called_times):
        _requests_post.reset_mock()
        sync_mda_user_to_shop_relation()
        self.assertEqual(_requests_post.call_count, called_times)

    def test_sync_task(self, _requests_post):
        WorkerDay.objects.filter(id=self.wd.id).update(dt=self.dt_now)
        self._test_sync_task(_requests_post, 1)

        WorkerDay.objects.filter(id=self.wd.id).update(dt=self.dt_now + timedelta(days=1))
        self._test_sync_task(_requests_post, 0)

        WorkerDay.objects.filter(id=self.wd.id).update(dt=self.dt_now - timedelta(days=1))
        self._test_sync_task(_requests_post, 0)

        # обучение факт подтв.
        WorkerDay.objects.create(
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt_now,
            type_id=WorkerDay.TYPE_QUALIFICATION,
            shop=self.shop2,
            dttm_work_start=datetime.combine(self.dt_now, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt_now, time(18, 0, 0)),
            is_vacancy=False,
            is_fact=True, is_approved=True,
        )
        self._test_sync_task(_requests_post, 0)

        # обучение в другом. магазине
        WorkerDay.objects.create(
            employee=self.employee3,
            employment=self.employment3,
            dt=self.dt_now,
            type_id=WorkerDay.TYPE_QUALIFICATION,
            shop=self.shop2,
            dttm_work_start=datetime.combine(self.dt_now, time(9, 0, 0)),
            dttm_work_end=datetime.combine(self.dt_now, time(18, 0, 0)),
            is_vacancy=False,
            is_fact=False, is_approved=True,
        )
        self._test_sync_task(_requests_post, 1)

        # обучение без магазина
        WorkerDay.objects.create(
            employee=self.employee4,
            employment=self.employment4,
            dt=self.dt_now,
            type_id=WorkerDay.TYPE_QUALIFICATION,
            shop=None,
            dttm_work_start=datetime.combine(self.dt_now, time(hour=9)),
            dttm_work_end=datetime.combine(self.dt_now, time(8, 0, 0)),
            is_vacancy=False,
            is_fact=False, is_approved=True,
        )
        self._test_sync_task(_requests_post, 1)

        # простой рабочий день
        work_type_reg_shop1 = WorkType.objects.create(shop=self.reg_shop1, work_type_name=self.work_type_name1)
        wd = WorkerDay.objects.create(
            employee=self.employee5,
            employment=self.employment5,
            dt=self.dt_now,
            type_id=WorkerDay.TYPE_WORKDAY,
            shop=self.reg_shop1,
            dttm_work_start=datetime.combine(self.dt_now, time(hour=9)),
            dttm_work_end=datetime.combine(self.dt_now, time(8, 0, 0)),
            is_vacancy=False,
            is_fact=False, is_approved=True,
        )
        WorkerDayCashboxDetails.objects.create(
            work_type=work_type_reg_shop1,
            worker_day=wd,
            work_part=1,
        )
        self._test_sync_task(_requests_post, 1)
