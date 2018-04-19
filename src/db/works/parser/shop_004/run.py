import os

from src.db.models import SuperShop
from . import users, users_2, demand, demand_2, demand_3, queue


def run():
    path = os.path.dirname(os.path.abspath(__file__))

    try:
        super_shop = SuperShop.objects.get(hidden_title='shop004')
    except SuperShop.DoesNotExist:
        super_shop = SuperShop.objects.create(title='Алтуфьево', hidden_title='shop004')

    users.run(path, super_shop)
    users_2.run(path, super_shop)
    demand.run(path, super_shop)
    demand_2.run(path, super_shop)
    demand_3.run(path, super_shop)
    queue.run(path, super_shop)
