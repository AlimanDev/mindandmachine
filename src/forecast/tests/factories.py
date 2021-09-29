import json
import random

import factory

from src.forecast.models import Receipt, LoadTemplate


class ReceiptFactory(factory.django.DjangoModelFactory):
    code = factory.Faker('uuid4')
    dttm = factory.Faker('date_time_between', start_date='-1m', end_date='-1d')
    dt = factory.LazyAttribute(lambda o: o.dttm.date())
    info = factory.Sequence(lambda n: json.dumps({'СуммаДокумента': random.randint(1, 100)}))

    class Meta:
        model = Receipt


class LoadTemplateFactory(factory.django.DjangoModelFactory):
    name = factory.Faker('text', max_nb_chars=50)

    class Meta:
        model = LoadTemplate
