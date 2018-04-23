import os

from src.db.models import SuperShop, Shop, User
from . import users, demand, demand_2

def run():
    path = os.path.dirname(os.path.abspath(__file__))

    try:
        super_shop = SuperShop.objects.get(hidden_title='shop_magnit')
    except SuperShop.DoesNotExist:
        super_shop = SuperShop.objects.create(title='Магнит', hidden_title='shop_magnit')

    shop = Shop.objects.create(super_shop=super_shop, title='Общий', hidden_title='common')

    users.run(path, super_shop)
    print('add users \n\n')
    demand.run(path, super_shop)
    print('add demand \n\n')
    demand_2.run(path, super_shop)

    # user = User.objects.create_user(
    #     username='magnit',
    #     email='q@q.com',
    #     password='test'
    # )
    # user.shop = shop
    # user.work_type = User.WorkType.TYPE_5_2.value
    # user.first_name = 'Иван'
    # user.middle_name = 'Иванович'
    # user.last_name = 'Иванов'
    # user.save()
