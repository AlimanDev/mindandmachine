import os

from src.db.models import SuperShop
from . import users, users_2, demand


def run():
    path = os.path.dirname(os.path.abspath(__file__))

    super_shop = SuperShop.objects.create(title='Красногорск', hidden_title='shop003')
    users.run(path, super_shop)
    users_2.run(path, super_shop)
    demand.run(path, super_shop)
