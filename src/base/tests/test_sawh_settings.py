from datetime import date

from django.db.models import Q
from django.test import override_settings, TestCase

from etc.scripts import fill_calendar
from src.base.models import (
    Network,
    SAWHSettings,
    SAWHSettingsMapping,
)
from src.base.tests.factories import (
    NetworkFactory,
    UserFactory,
    ShopFactory,
    EmploymentFactory,
    GroupFactory,
    WorkerPositionFactory,
)
from src.timetable.models import WorkerDay, Employment
from src.timetable.tests.factories import WorkerDayFactory
from src.timetable.worker_day.stat import (
    WorkerProdCalExactHoursGetter,
    WorkerProdCalMeanHoursGetter,
    WorkerSawhHoursGetter,
)
from src.util.mixins.tests import TestsHelperMixin


class SawhSettingsHelperMixin(TestsHelperMixin):
    acc_period = None

    @classmethod
    def setUpTestData(cls):
        cls.network = NetworkFactory(
            accounting_period_length=cls.acc_period,
        )
        cls.shop = ShopFactory(
            network=cls.network,
            tm_open_dict='{"all": "08:00:00"}',
            tm_close_dict='{"all": "22:00:00"}',
        )
        cls.group = GroupFactory(network=cls.network)
        cls.worker_position = WorkerPositionFactory(group=cls.group)
        cls.worker = UserFactory(network=cls.network)
        cls.employment = EmploymentFactory(
            dt_hired='2001-01-01', dt_fired='3999-12-12',
            network=cls.network, user=cls.worker, shop=cls.shop, position=cls.worker_position)
        cls.dt = date(2021, 1, 1)
        cls.add_group_perm(cls.group, 'ShopSchedule', 'GET')
        cls.add_group_perm(cls.group, 'ShopSchedule', 'PUT')

        cls.sawh_settings, _sawh_settings_created = SAWHSettings.objects.update_or_create(
            network=cls.network,
            work_hours_by_months={f'm{month_num}': 1 / cls.network.accounting_period_length for month_num in
                                  range(1, 12 + 1)}
        )
        cls.sawh_settings_mapping = SAWHSettingsMapping.objects.create(
            year=2021,
            sawh_settings=cls.sawh_settings,
        )
        cls.sawh_settings_mapping.shops.add(cls.shop)

        fill_calendar.fill_days('2021.01.01', '2021.12.31', cls.shop.region_id)

    def setUp(self):
        self.network.refresh_from_db()
        self.sawh_settings.refresh_from_db()
        self.shop.refresh_from_db()
        self.worker_position.refresh_from_db()
        self.employment.refresh_from_db()

    def _set_obj_data(self, obj, **data):
        for i, v in data.items():
            setattr(obj, i, v)
        obj.save(update_fields=list(data.keys()))

    def _set_network_settings(self, **data):
        self._set_obj_data(self.network, **data)

    def _test_norm_hours_for_period(
            self, dt_from, dt_to, expected_res, norm_hours_cls=WorkerProdCalExactHoursGetter):
        acc_period_start, acc_period_end = self.network.get_acc_period_range(dt_from)
        norm_hours_getter = norm_hours_cls(
            worker_id=self.worker.id,
            network=self.network,
            worker_days=list(WorkerDay.objects.filter(
                worker_id=self.worker.id,
                type__in=WorkerDay.TYPES_USED,
                dt__gte=dt_from,
                dt__lte=dt_to,
                is_fact=False,
                is_approved=True,
            ).exclude(
                Q(type__in=WorkerDay.TYPES_WITH_TM_RANGE) &
                Q(
                    Q(dttm_work_start__isnull=True) |
                    Q(dttm_work_end__isnull=True)
                )
            ).select_related(
                'employment',
            )),
            employments_list=list(Employment.objects.get_active(
                dt_from=acc_period_start,
                dt_to=acc_period_end,
                user_id=self.worker.id,
            ).select_related('position')),
            region_id=self.shop.region_id,
            dt_from=dt_from,
            dt_to=dt_to,
            acc_period_start=acc_period_start,
            acc_period_end=acc_period_end,
        )
        res = norm_hours_getter.run()
        self.assertDictEqual(res, expected_res)
        return res

    def _test_norm_hours_for_acc_period(self, dt, expected_res, **kwargs):
        dt_from, dt_to = self.network.get_acc_period_range(dt)
        self._test_norm_hours_for_period(dt_from=dt_from, dt_to=dt_to, expected_res=expected_res, **kwargs)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWHSettingsMonthAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_MONTH

    def test_norm_hours_for_acc_period(self):
        for norm_hours_cls in [WorkerProdCalExactHoursGetter, WorkerProdCalMeanHoursGetter]:
            self._test_norm_hours_for_acc_period(dt=date(2021, 1, 1), expected_res={'value': 120.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 2, 1), expected_res={'value': 151.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 3, 1), expected_res={'value': 176.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 4, 1), expected_res={'value': 175.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 5, 1), expected_res={'value': 152.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 6, 1), expected_res={'value': 167.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 7, 1), expected_res={'value': 176.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 8, 1), expected_res={'value': 176.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 9, 1), expected_res={'value': 176.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 10, 1), expected_res={'value': 168.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 11, 1), expected_res={'value': 159.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 12, 1), expected_res={'value': 176.0},
                                                 norm_hours_cls=norm_hours_cls)

    def test_norm_for_36_hours_week(self):
        self.worker_position.hours_in_a_week = 36
        self.worker_position.save()
        for norm_hours_cls in [WorkerProdCalExactHoursGetter, WorkerProdCalMeanHoursGetter]:
            self._test_norm_hours_for_period(
                dt_from=date(2021, 2, 1),
                dt_to=date(2021, 2, 28),
                expected_res={'value': 135.8},
                norm_hours_cls=norm_hours_cls,
            )

    def test_subtract_sick_days_from_norm_hours_exact(self):
        # часть новогодн. праздников
        for day_num in range(1, 5):
            WorkerDayFactory(
                worker=self.worker,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        # выходные
        for day_num in range(30, 32):
            WorkerDayFactory(
                worker=self.worker,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        self._test_norm_hours_for_acc_period(
            dt=date(2021, 1, 1), expected_res={'value': 120.0},
            norm_hours_cls=WorkerProdCalExactHoursGetter)

        # рабочая неделя
        for day_num in range(25, 30):
            WorkerDayFactory(
                worker=self.worker,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        self._test_norm_hours_for_acc_period(
            dt=date(2021, 1, 1), expected_res={'value': 80.0},
            norm_hours_cls=WorkerProdCalExactHoursGetter)

    def test_subtract_sick_days_from_norm_hours_mean(self):
        # часть новогодн. праздников
        for day_num in range(1, 5):
            WorkerDayFactory(
                worker=self.worker,
                employment=self.employment,
                shop=self.shop,
                type=WorkerDay.TYPE_SICK,
                dt=date(2021, 1, day_num),
                is_fact=False,
                is_approved=True,
            )

        self._test_norm_hours_for_acc_period(
            dt=date(2021, 1, 1),
            expected_res={'value': 104.51612903225805},
            norm_hours_cls=WorkerProdCalMeanHoursGetter,
        )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWGSettingsQuarterAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_QUARTER

    def test_norm_hours_for_acc_period(self):
        for norm_hours_cls in [WorkerProdCalExactHoursGetter, WorkerProdCalMeanHoursGetter]:
            self._test_norm_hours_for_acc_period(dt=date(2021, 1, 1), expected_res={'value': 447.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 4, 1), expected_res={'value': 494.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 7, 1), expected_res={'value': 528.0},
                                                 norm_hours_cls=norm_hours_cls)
            self._test_norm_hours_for_acc_period(dt=date(2021, 10, 1), expected_res={'value': 503.0},
                                                 norm_hours_cls=norm_hours_cls)

    def test_equal_distribution_by_months(self):
        self.sawh_settings.work_hours_by_months = {
            f'm{month_num}': 100 / self.network.accounting_period_length for month_num in range(1, 12 + 1)}
        self.sawh_settings.save(update_fields=['work_hours_by_months'])
        self._test_norm_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_res={'value': 149.00000000000003},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        self._test_norm_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_res={'value': 149.00000000000003},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        self._test_norm_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_res={'value': 149.00000000000003},
            norm_hours_cls=WorkerSawhHoursGetter,
        )

    def test_two_employments_case_one(self):
        self.sawh_settings.work_hours_by_months['m1'] = 0.3125
        self.sawh_settings.work_hours_by_months['m2'] = 0.375
        self.sawh_settings.work_hours_by_months['m3'] = 0.3125
        self.sawh_settings.save()
        self.employment.dt_hired = '2021-01-01'
        self.employment.dt_fired = '2021-02-09'
        self.employment.save()
        worker_position2 = WorkerPositionFactory(network=self.network)
        sawh_settings2 = SAWHSettings.objects.create(
            network=self.network,
            work_hours_by_months={
              'm1': 0.3125,
              'm2': 0.3125,
              'm3': 0.375,
            },
        )
        sawh_settings_mapping2 = SAWHSettingsMapping.objects.create(
            sawh_settings=sawh_settings2,
            priority=10,
        )
        sawh_settings_mapping2.positions.add(worker_position2)
        EmploymentFactory(
            dt_hired='2021-02-10', dt_fired='3999-12-12',
            network=self.network, user=self.worker, shop=self.shop, position=worker_position2)
        res = self._test_norm_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_res={'value': 136.93654266958424},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        res2 = self._test_norm_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_res={'value': 145.73960612691468},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        res3 = self._test_norm_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_res={'value': 164.32385120350108},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        self.assertEqual(res['value'] + res2['value'] + res3['value'], 447)

    def test_two_employments_case_two(self):
        self.sawh_settings.work_hours_by_months['m1'] = 0.3
        self.sawh_settings.work_hours_by_months['m2'] = 0.3
        self.sawh_settings.work_hours_by_months['m3'] = 0.4
        self.sawh_settings.save()
        self.employment.dt_hired = '2021-01-01'
        self.employment.dt_fired = '2021-02-09'
        self.employment.save()
        worker_position2 = WorkerPositionFactory(network=self.network)
        sawh_settings2 = SAWHSettings.objects.create(
            network=self.network,
            work_hours_by_months={
              'm1': 0.3125,
              'm2': 0.375,
              'm3': 0.3125,
            },
        )
        sawh_settings_mapping2 = SAWHSettingsMapping.objects.create(
            sawh_settings=sawh_settings2,
            priority=10,
        )
        sawh_settings_mapping2.positions.add(worker_position2)
        EmploymentFactory(
            dt_hired='2021-02-10', dt_fired='2021-03-20',
            network=self.network, user=self.worker, shop=self.shop, position=worker_position2)
        res = self._test_norm_hours_for_period(
            dt_from=date(2021, 1, 1),
            dt_to=date(2021, 1, 31),
            expected_res={'value': 134.7791479441873},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        res2 = self._test_norm_hours_for_period(
            dt_from=date(2021, 2, 1),
            dt_to=date(2021, 2, 28),
            expected_res={'value': 157.64346768471904},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        res3 = self._test_norm_hours_for_period(
            dt_from=date(2021, 3, 1),
            dt_to=date(2021, 3, 31),
            expected_res={'value': 90.5773843710936},
            norm_hours_cls=WorkerSawhHoursGetter,
        )
        self.assertEqual(res['value'] + res2['value'] + res3['value'], 382.99999999999994)


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWGSettingsHalfYearAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_HALF_YEAR

    def test_norm_hours_for_acc_period(self):
        for norm_hours_cls in [WorkerProdCalExactHoursGetter, WorkerProdCalMeanHoursGetter]:
            self._test_norm_hours_for_acc_period(
                dt=date(2021, 1, 1),
                expected_res={'value': 941.0},
                norm_hours_cls=norm_hours_cls,
            )
            self._test_norm_hours_for_acc_period(
                dt=date(2021, 7, 1),
                expected_res={'value': 1031.0},
                norm_hours_cls=norm_hours_cls,
            )


@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
class TestSAWGSettingsYearAccPeriod(SawhSettingsHelperMixin, TestCase):
    acc_period = Network.ACC_PERIOD_YEAR

    def test_norm_hours_for_acc_period(self):
        for norm_hours_cls in [WorkerProdCalExactHoursGetter, WorkerProdCalMeanHoursGetter]:
            self._test_norm_hours_for_acc_period(
                dt=date(2021, 1, 1),
                expected_res={'value': 1972.0},
                norm_hours_cls=norm_hours_cls,
            )
