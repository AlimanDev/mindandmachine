import os

from src.db.models import SuperShop
from src.db.works.parser.shop_003 import demand_2


def run():
    path = os.path.dirname(os.path.abspath(__file__))

    super_shop = SuperShop.objects.get(title='Красногорск', hidden_title='shop003')

    demand_2.run(path, super_shop)
