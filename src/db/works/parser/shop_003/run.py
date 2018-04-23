import os

from src.db.models import SuperShop
from . import users, users_2, demand, demand_2, demand_3


def run():
    path = os.path.dirname(os.path.abspath(__file__))

    try:
        super_shop = SuperShop.objects.get(hidden_title='shop003')
    except SuperShop.DoesNotExist:
        super_shop = SuperShop.objects.create(title='Красногорск', hidden_title='shop003')

    users.run(path, super_shop)
    users_2.run(path, super_shop)
    demand.run(path, super_shop)
    demand_2.run(path, super_shop)
    demand_3.run(path, super_shop)
