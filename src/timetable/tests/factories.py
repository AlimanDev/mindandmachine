import random
from datetime import datetime, time

import factory

from src.base.tests.factories_abstract import AbstractActiveNamedModelFactory
from src.timetable.models import WorkerDay, WorkerDayCashboxDetails, WorkType, WorkTypeName, EmploymentWorkType


class WorkTypeNameFactory(AbstractActiveNamedModelFactory):
    name = factory.LazyFunction(lambda: random.choice(['Кассир', 'Директор', 'Врач']))

    class Meta:
        model = WorkTypeName
        django_get_or_create = ('name',)


class WorkTypeFactory(factory.django.DjangoModelFactory):
    shop = factory.SubFactory('src.base.tests.factories.ShopFactory')
    work_type_name = factory.SubFactory('src.timetable.tests.factories.WorkTypeNameFactory')

    class Meta:
        model = WorkType
        django_get_or_create = ('shop', 'work_type_name')


class WorkerDayCashboxDetailsFactory(factory.django.DjangoModelFactory):
    worker_day = factory.SubFactory('src.timetable.tests.factories.WorkerDayFactory')
    work_type = factory.SubFactory('src.timetable.tests.factories.WorkTypeFactory')

    class Meta:
        model = WorkerDayCashboxDetails


class WorkerDayFactory(factory.django.DjangoModelFactory):
    shop = factory.SubFactory('src.base.tests.factories.ShopFactory')
    employment = factory.SubFactory('src.base.tests.factories.EmploymentFactory')
    dt = factory.Faker('date_between', start_date='-120d', end_date='+30d')
    dttm_work_start = factory.LazyAttribute(
        lambda wd: datetime.combine(wd.dt, time(10, 0, 0)) if WorkerDay.is_type_with_tm_range(wd.type) else None
    )
    dttm_work_end = factory.LazyAttribute(
        lambda wd: datetime.combine(wd.dt, time(20, 0, 0)) if WorkerDay.is_type_with_tm_range(wd.type) else None
    )
    employee = factory.SubFactory('src.base.tests.factories.EmployeeFactory')
    type = factory.LazyFunction(lambda: random.choice(WorkerDay.TYPES_USED))

    class Meta:
        model = WorkerDay

    @factory.post_generation
    def cashbox_details(self, create, *args, **kwargs):
        if not create:
            return

        if self.type == WorkerDay.TYPE_WORKDAY:
            WorkerDayCashboxDetailsFactory(
                worker_day=self,
                work_type__shop=self.shop,
                **kwargs,
            )


class EmploymentWorkTypeFactory(factory.django.DjangoModelFactory):
    work_type = factory.SubFactory('src.timetable.tests.factories.WorkTypeFactory')

    class Meta:
        model = EmploymentWorkType
        django_get_or_create = ('employment', 'work_type')
