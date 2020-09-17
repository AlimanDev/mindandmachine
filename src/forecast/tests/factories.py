import json
import random

import factory

from src.forecast.models import Receipt


class ReceiptFactory(factory.django.DjangoModelFactory):
    code = factory.Faker('uuid4')
    dttm = factory.Faker('date_time_between', start_date='-1m', end_date='-1d')
    info = factory.Sequence(lambda n: json.dumps({'СуммаДокумента': random.randint(1, 100)}))

    class Meta:
        model = Receipt
