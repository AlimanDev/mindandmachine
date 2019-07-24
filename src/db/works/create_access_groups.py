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

def password_generator(len=14):
    return str(uuid4()).replace('-', '')[:len]  # algo based on SHA-1 (not safe enough nowdays)


def main(hq_accs=2):
    """

    :param hq_accs: кол-во аккаунтов для ЦО
    :return:
    """

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
            access_type=FunctionGroup.TYPE_ALL
        ) for func in FunctionGroup.FUNCS
    ])

    # central office
    hq_group = Group.objects.create(name='ЦО')
    for func in FunctionGroup.FUNCS:
        if 'get' in func or func == 'signin' or func == 'signout':
            FunctionGroup.objects.create(
                group=hq_group,
                func=func,
                access_type=FunctionGroup.TYPE_ALL
            )

    # chiefs
    chief_group = Group.objects.create(name='Руководитель')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=chief_group,
            func=func,
            access_type=FunctionGroup.TYPE_SUPERSHOP
        ) for func in FunctionGroup.FUNCS
    ])

    # employee
    employee_group = Group.objects.create(name='Сотрудник')
    FunctionGroup.objects.bulk_create([
        FunctionGroup(
            group=employee_group,
            func=func,
            access_type=FunctionGroup.TYPE_SELF
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
    )
    u_pass = password_generator()
    admin.set_password(u_pass)
    admin.save()
    print('admin login: {}, password: {}'.format('qadmin', u_pass))


    for i in range(1, hq_accs + 1):
        username = 'hq_{}'.format(i)
        hq_acc = User.objects.create(
            username=username,
            first_name='ЦО',
            last_name='',
            function_group=hq_group
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

