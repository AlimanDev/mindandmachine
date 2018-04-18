import os

from src.db.models import SuperShop
from . import demand
from . import users
from . import queue


def run():
    path = os.path.dirname(os.path.abspath(__file__))

    super_shop = SuperShop.objects.create(title='Алтуфьево', hidden_title='shop004')
    users.run(path, super_shop)
    demand.run(path, super_shop)
    queue.run(path, super_shop)
