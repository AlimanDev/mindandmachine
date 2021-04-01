import random
from datetime import datetime, timedelta, time

import factory

from src.base.models import (
    Shop,
    Employment,
    User,
    Region,
    Network,
    WorkerPosition,
    Group,
    Break,
    ShopSettings,
    ShopSchedule,
)
from src.timetable.tests.factories import EmploymentWorkTypeFactory
from .factories_abstract import AbstractActiveNamedModelFactory


class BreakFactory(AbstractActiveNamedModelFactory):
    value = '[[0, 360, [30]], [360, 540, [30, 30]], [540, 2040, [30, 30, 15]]]'
    code = 'default'

    class Meta:
        model = Break
        django_get_or_create = ('code',)


class GroupFactory(AbstractActiveNamedModelFactory):
    name = factory.Faker('job', locale='ru_RU')

    class Meta:
        model = Group
        django_get_or_create = ('code',)


class WorkerPositionFactory(AbstractActiveNamedModelFactory):
    name = factory.Faker('job', locale='ru_RU')
    group = factory.SubFactory('src.base.tests.factories.GroupFactory')

    class Meta:
        model = WorkerPosition


class NetworkFactory(factory.django.DjangoModelFactory):
    name = 'Сеть по умолчанию'
    code = 'default'

    class Meta:
        model = Network
        django_get_or_create = ('code',)


class RegionFactory(AbstractActiveNamedModelFactory):
    name = 'Россия'
    code = 'default'

    class Meta:
        model = Region
        django_get_or_create = ('code',)


class ShopFactory(AbstractActiveNamedModelFactory):
    name = factory.LazyAttribute(lambda s: f'{s.code} {s.address}')
    address = factory.Faker('address', locale='ru_RU')
    type = factory.LazyFunction(lambda: random.choice(Shop.DEPARTMENT_TYPES)[0])
    dt_opened = factory.Faker('date_between', start_date='-3y', end_date='-1y')
    dt_closed = None
    tm_open_dict = factory.LazyFunction(
        lambda: '{{"all": "{:02d}:00:00"}}'.format(random.choice([7, 8, 9, 10, 11, 12])))
    tm_close_dict = factory.LazyFunction(lambda: '{{"all": "{:02d}:00:00"}}'.format(random.choice([19, 20, 21, 22])))
    region = factory.LazyFunction(lambda: RegionFactory(name='Россия'))
    email = factory.Faker('email')
    latitude = factory.Faker('latitude')
    longitude = factory.Faker('longitude')
    settings = factory.SubFactory('src.base.tests.factories.ShopSettingsFactory')

    class Meta:
        model = Shop


class EmploymentFactory(factory.django.DjangoModelFactory):
    network = factory.SubFactory('src.base.tests.factories.NetworkFactory')
    user = factory.SubFactory('src.base.tests.factories.UserFactory')
    shop = factory.SubFactory('src.base.tests.factories.ShopFactory')
    function_group = factory.SubFactory('src.base.tests.factories.GroupFactory')
    position = factory.SubFactory('src.base.tests.factories.WorkerPositionFactory')

    class Meta:
        model = Employment

    @factory.post_generation
    def work_types(self, create, *args, **kwargs):
        if not create:
            return

        EmploymentWorkTypeFactory(
            employment=self,
            work_type__shop=self.shop,
            **kwargs,
        )


class UserFactory(factory.django.DjangoModelFactory):
    network = factory.SubFactory('src.base.tests.factories.NetworkFactory')
    username = factory.Faker('user_name')
    email = factory.Faker('email')
    first_name = factory.Faker('first_name', locale='ru_RU')
    middle_name = factory.Faker('middle_name', locale='ru_RU')
    last_name = factory.Faker('last_name', locale='ru_RU')
    phone_number = factory.Faker('phone_number')
    tabel_code = factory.LazyAttribute(lambda u: u.username)

    class Meta:
        model = User
        django_get_or_create = ('username',)


class ShopSettingsFactory(factory.django.DjangoModelFactory):
    breaks = factory.SubFactory('src.base.tests.factories.BreakFactory')

    class Meta:
        model = ShopSettings


class ShopScheduleFactory(factory.django.DjangoModelFactory):
    modified_by = None
    shop = factory.SubFactory('src.base.tests.factories.ShopFactory')
    dt = factory.Sequence(lambda n: datetime.now().date() + timedelta(n))
    opens = factory.LazyAttribute(lambda o: time(9) if o.type == ShopSchedule.WORKDAY_TYPE else None)
    closes = factory.LazyAttribute(lambda o: time(21) if o.type == ShopSchedule.WORKDAY_TYPE else None)
    type = ShopSchedule.WORKDAY_TYPE

    class Meta:
        model = ShopSchedule
