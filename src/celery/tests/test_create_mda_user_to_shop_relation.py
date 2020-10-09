from datetime import time, datetime
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from src.timetable.models import WorkerDay
from src.util.mixins.tests import TestsHelperMixin


@mock.patch('src.celery.tasks.requests.post')
class TestCreateMDAUserToShopRelation(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dt_now = timezone.now().date()
        cls.create_departments_and_users()
        cls.wd = WorkerDay.objects.create(
            worker=cls.user2,
            employment=cls.employment2,
            dt=cls.dt_now,
            type=WorkerDay.TYPE_WORKDAY,
            shop=cls.shop,
            dttm_work_start=datetime.combine(cls.dt_now, time(hour=9)),
            dttm_work_end=datetime.combine(cls.dt_now, time(8, 0, 0)),
            is_vacancy=True,
        )

    def test_create_mda_user_to_shop_rel_called_with_enabled_setting(self, _requests_post):
        with self.settings(MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE=True, CELERY_TASK_ALWAYS_EAGER=True):
            self.wd.save()

        _requests_post.assert_called_once()

    def test_create_mda_user_to_shop_rel_not_called_with_disabled_setting(self, _requests_post):
        with self.settings(MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE=False, CELERY_TASK_ALWAYS_EAGER=True):
            self.wd.save()

        _requests_post.assert_not_called()

    def test_create_mda_user_to_shop_rel_not_called_for_not_vacancy(self, _requests_post):
        self.wd.is_vacancy = False
        with self.settings(MDA_SEND_USER_TO_SHOP_REL_ON_WD_SAVE=True, CELERY_TASK_ALWAYS_EAGER=True):
            self.wd.save()

        _requests_post.assert_not_called()
