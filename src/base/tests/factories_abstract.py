import factory


class AbstractActiveNamedModelFactory(factory.django.DjangoModelFactory):
    network = factory.SubFactory('src.base.tests.factories.NetworkFactory')
    name = factory.Faker('text', max_nb_chars=50)
    code = factory.Faker('uuid4')
