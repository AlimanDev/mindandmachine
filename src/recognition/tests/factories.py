import factory

from src.recognition.models import TickPoint


class TickPointFactory(factory.django.DjangoModelFactory):
    name = factory.Faker('text', max_nb_chars=50)
    shop = factory.SubFactory('src.base.tests.factories.ShopFactory')
    network = factory.SubFactory('src.base.tests.factories.NetworkFactory')
    key = factory.Faker('uuid4')

    class Meta:
        model = TickPoint
