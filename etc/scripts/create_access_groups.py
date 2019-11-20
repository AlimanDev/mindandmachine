"""
Данные скрипт служит для создании дефолтных групп доступа:
1. админы -- все могут короли
2. ЦО -- все могут смотреть (ничего править)
3. Руководители точек -- все могут в рамках точки
4. сотрудники -- в рамках себя могут смотреть информацию

А так же создает аккаунт для админа и 2 для ЦО
"""


from uuid import uuid4
from django.utils import timezone
from src.db.models import Shop


def password_generator(len=14):
    return str(uuid4()).replace('-', '')[:len]  # algo based on SHA-1 (not safe enough nowdays)


def main(hq_accs=2):
    """

    :param hq_accs: кол-во аккаунтов для ЦО
    :return:
    """

    root_shop = Shop.objects.filter(level=0).first()
    middle_shops = Shop.objects.filter(level=1)
    leaf_shop = Shop.objects.filter(level=2).first()

    from src.db.models import (
        User,
        Group,
        FunctionGroup
    )

    # creating groups
    # admins
    admin_group = Group.objects.create(name='Администратор')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=admin_group,
            func=func,
            level_up=1,
            level_down=100,
        ) for func in FunctionGroup.FUNCS
    ])


    # employee
    employee_group = Group.objects.create(name='Сотрудник')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=employee_group,
            func=func,
            level_up=0,
            level_down=0,
        ) for func in FunctionGroup.FUNCS
    ])


    # creating users
    admin = User.objects.create(
        is_staff=True,
        is_superuser=True,
        username='qadmin',
        function_group=admin_group,
        first_name='Admin',
        last_name='Admin',
        dt_hired=timezone.now().date(),
        shop = root_shop
    )
    u_pass = password_generator()
    admin.set_password(u_pass)
    admin.save()
    print('admin login: {}, password: {}'.format('qadmin', u_pass))


    for i in range(0, len(middle_shops)):
        username = 'hq_{}'.format(i+1)
        hq_acc = User.objects.create(
            username=username,
            first_name='ЦО',
            last_name='',
            function_group=admin_group,
            shop = middle_shops[i]
        )

        u_pass = password_generator()
        hq_acc.set_password(u_pass)
        hq_acc.save()
        print('CO login: {}, password: {}'.format(username, u_pass))


if __name__ == "__main__":
    import os, django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.conf.djconfig")
    django.setup()

    print('start creating groups \n\n')
    main()
    print('\n\nfinish creating groups')

