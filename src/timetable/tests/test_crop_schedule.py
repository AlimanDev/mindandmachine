from datetime import timedelta, time, datetime

from rest_framework.test import APITestCase

from src.base.models import (
    ShopSchedule,
)
from src.timetable.models import (
    WorkerDay,
    WorkType,
    WorkTypeName,
    WorkerDayCashboxDetails,
)
from src.util.mixins.tests import TestsHelperMixin

class TestCropSchedule(TestsHelperMixin, APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dt_now = datetime.now().date()
        cls.work_type_name = WorkTypeName.objects.create(name='Магазин', network=cls.network)
        cls.work_type = WorkType.objects.create(work_type_name=cls.work_type_name, shop=cls.shop)

        # всегда 1 ч перерыв, чтобы было легче считать
        cls.shop.network.crop_work_hours_by_shop_schedule = True
        cls.shop.network.only_fact_hours_that_in_approved_plan = False
        cls.shop.network.save()
        cls.shop.settings.breaks.value = '[[0, 2000, [30, 30]]]'
        cls.shop.settings.breaks.save()

    def _test_crop_hours(
            self, shop_open_h, shop_close_h, work_start_h, work_end_h, expected_work_h, bulk=False):
        self.shop.tm_open_dict = f'{{"all":"{shop_open_h}:00:00"}}' if isinstance(shop_open_h, int) else shop_open_h
        self.shop.tm_close_dict = f'{{"all":"{shop_close_h}:00:00"}}' if isinstance(shop_close_h, int) else shop_close_h
        self.shop.save()

        WorkerDay.objects.filter(
            dt=self.dt_now,
            employee=self.employee2,
            is_fact=True,
            is_approved=True,
        ).delete()

        wd_kwargs = dict(
            shop=self.shop,
            employee=self.employee2,
            employment=self.employment2,
            dt=self.dt_now,
            is_fact=True,
            is_approved=True,
            type_id=WorkerDay.TYPE_WORKDAY,
            dttm_work_start=datetime.combine(self.dt_now, time(work_start_h, 00, 0)) \
                if isinstance(work_start_h, int) else work_start_h,
            dttm_work_end=datetime.combine(self.dt_now, time(work_end_h, 00, 0))
                if isinstance(work_end_h, int) else work_end_h,
        )
        if bulk:
            wd_kwargs['need_count_wh'] = True
        wd = WorkerDay(**wd_kwargs)
        if bulk:
            wd = WorkerDay.objects.bulk_create([wd])[0]
        else:
            wd.save()
        WorkerDayCashboxDetails.objects.create(
            work_type=self.work_type,
            worker_day=wd,
            work_part=1,
        )
        self.assertEqual(
            timedelta(hours=expected_work_h) if isinstance(expected_work_h, int) else expected_work_h,
            wd.work_hours
        )

    def _test_crop_both_bulk_and_original_save(self, *args, **kwargs):
        self._test_crop_hours(*args, bulk=False, **kwargs)
        self._test_crop_hours(*args, bulk=True, **kwargs)

    def test_crop_work_hours_by_shop_schedule(self):
        # параметры: час откр. магазина, час закр. магазина, час начала работы, час конца работы, ожидаемое к-во часов
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 9)
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 12)
        self._test_crop_both_bulk_and_original_save(10, 20, 11, 19, 7)
        self._test_crop_both_bulk_and_original_save(10, 20, 11, 19, 7)
        self._test_crop_both_bulk_and_original_save(10, 22, 10, 23, 11)
        self._test_crop_both_bulk_and_original_save(10, 22, 10, 23, 12)
        self._test_crop_both_bulk_and_original_save(
            10, 23, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 2)
        self._test_crop_both_bulk_and_original_save(
            10, 23, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 6)

        # круглосуточный магазин или расписание не заполнено
        self._test_crop_both_bulk_and_original_save(
            0, 0, 20, datetime.combine(self.dt_now + timedelta(days=1), time(3, 00, 0)), 6)

        # проверка по дням недели
        weekday = self.dt_now.weekday()
        self._test_crop_both_bulk_and_original_save(
            f'{{"{weekday}":"12:00:00"}}', f'{{"{weekday}":"23:00:00"}}', 10, 20, 7)

        # факт. время работы с минутами
        self._test_crop_both_bulk_and_original_save(
            10, 22,
            datetime.combine(self.dt_now, time(9, 46, 15)),
            datetime.combine(self.dt_now, time(21, 47, 23)),
            timedelta(seconds=38843),
        )
        self._test_crop_both_bulk_and_original_save(
            10, 22,
            datetime.combine(self.dt_now, time(9, 46, 15)),
            datetime.combine(self.dt_now, time(21, 47, 23)),
            timedelta(seconds=39668),
        )

        # todo: ночные смены (когда-нибудь)

    def test_zero_hours_for_holiday(self):
        ShopSchedule.objects.update_or_create(
            dt=self.dt_now,
            shop=self.shop,
            defaults=dict(
                type='H',
                opens=None,
                closes=None,
                modified_by=self.user1,
            ),
        )
        self._test_crop_both_bulk_and_original_save(10, 20, 8, 21, 0)
