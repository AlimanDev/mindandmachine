import uuid
from calendar import monthrange
from datetime import datetime, timedelta
import pandas as pd

from django.test import TestCase

from src.base.models import Employment
from src.timetable.models import WorkTypeName, WorkType, WorkerDay
from src.util.dg.tabel import T13TabelGenerator, CustomT13TabelGenerator, MTSTabelGenerator, AigulTabelGenerator
from src.util.mixins.tests import TestsHelperMixin


class TestGenerateTabel(TestsHelperMixin, TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.create_departments_and_users()
        cls.dttm_now = datetime.now()
        cls.dt_now = cls.dttm_now.date()
        for e in Employment.objects.all():
            e.tabel_code = f'A000{e.id}'
            e.save()
        Employment.objects.create(
            network=cls.network,
            code=f'{cls.user2.username}:{uuid.uuid4()}:{uuid.uuid4()}',
            user=cls.user2,
            shop=cls.shop,
            function_group=cls.employee_group,
            dt_hired=cls.dt_now,
            salary=100,
            tabel_code='A00001234',
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
        df = pd.read_excel(g.generate(convert_to='xlsx')).fillna('')
        rows = df.sample(10)
        for _, r in rows.iterrows():
            dt = r['Дата']
            shop_code = r['Код ОП']
            tabel_code = r['Табельный номер']
            fact_h = r['Факт, ч']
            plan_h = r['План, ч']
            wdays = WorkerDay.objects.filter(
                shop__code=shop_code,
                dt=dt,
                employment__tabel_code=tabel_code,
                is_approved=True,
            )
            fact = wdays.filter(is_fact=True).first()
            plan = wdays.filter(is_fact=False).first()
            if fact_h == 0.0:
                self.assertIsNone(fact)
            else:
                self.assertIsNotNone(fact)
                self.assertEqual(fact.work_hours, timedelta(seconds=fact_h * 3600))
            if plan_h == 0.0:
                self.assertIsNone(plan)
            else:
                self.assertIsNotNone(plan)
                self.assertEqual(plan.work_hours, timedelta(seconds=plan_h * 3600))


    def test_generate_custom_t13_tabel(self):
        g = CustomT13TabelGenerator(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        df = pd.read_excel(g.generate(convert_to='xlsx'))
        df = df.dropna(axis=1, how='all')
        df = df.dropna(axis=0, how='all')
        df = df.loc[1:, :]
        df.columns = df.iloc[0]
        df = df.drop(1).reset_index(drop=True)
        self.assertEqual(df.loc[12, df.columns[1]], df.loc[16, df.columns[1]])
        

    def test_generate_aigul_tabel(self):
        g = AigulTabelGenerator(shop=self.shop, dt_from=self.dt_from, dt_to=self.dt_to)
        df = pd.read_excel(g.generate(convert_to='xlsx')).fillna('')
        df = df.drop(columns=df.columns[0]).loc[2:, :]
        df.columns = df.iloc[0]
        df = df.drop(2).reset_index(drop=True)
        self.assertEqual(df.loc[2, 'ФИО'], df.loc[3, 'ФИО'])
