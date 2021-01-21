import uuid
from calendar import monthrange
from datetime import datetime

from django.test import TestCase

from src.base.models import Employment
from src.timetable.models import WorkTypeName, WorkType
from src.util.dg.tabel import T13TabelGenerator, CustomT13TabelGenerator, MTSTabelGenerator, AigulTabelGenerator
from src.util.mixins.tests import TestsHelperMixin


class TestGenerateTabel(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dttm_now = datetime.now()
        cls.dt_now = cls.dttm_now.date()
        Employment.objects.create(
            network=cls.network,
            code=f'{cls.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            user=cls.user2,
            shop=cls.shop,
            function_group=cls.employee_group,
            dt_hired=cls.dt_now,
            salary=100,
        )
        _weekday, days_in_month = monthrange(cls.dt_now.year, cls.dt_now.month)
        cls.dt_from = cls.dt_now.replace(day=1)
        cls.dt_to = cls.dt_now.replace(day=days_in_month)
        cls.work_type_name = WorkTypeName.objects.create(name='Консультант')
        cls.work_type_name2 = WorkTypeName.objects.create(name='Кассир')
        cls.work_type = WorkType.objects.create(
            work_type_name=cls.work_type_name,
            shop=cls.shop)
        cls.work_type2 = WorkType.objects.create(
            work_type_name=cls.work_type_name2,
            shop=cls.shop)
        cls._generate_plan_and_fact_worker_days_for_shop_employments(
            shop=cls.shop, work_type=cls.work_type, dt_from=cls.dt_from, dt_to=cls.dt_to)
        cls.network.okpo = '44412749'

    def test_generate_mts_tabel(self):
        g = MTSTabelGenerator(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        content = g.generate(convert_to='xlsx')

        with open(f't_mts.xlsx', 'wb') as f:
            f.write(content)

    def test_generate_t13_tabel(self):
        g = T13TabelGenerator(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        content = g.generate(convert_to='pdf')

        with open(f't_13.pdf', 'wb') as f:
            f.write(content)

    def test_generate_custom_t13_tabel(self):
        g = CustomT13TabelGenerator(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        content = g.generate(convert_to='pdf')

        with open(f'custom_t_13.pdf', 'wb') as f:
            f.write(content)

    def test_generate_aigul_tabel(self):
        g = AigulTabelGenerator(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        content = g.generate(convert_to='xlsx')

        with open(f'aigul_t.xlsx', 'wb') as f:
            f.write(content)
