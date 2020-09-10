import factory

from .models import Receipt


class ReceiptFactory(factory.django.DjangoModelFactory):
    code = factory.Faker('uuid4')
    dttm = factory.Faker('date_time_between', start_date='-1y', end_date='-1m')

    class Meta:
        model = Receipt
