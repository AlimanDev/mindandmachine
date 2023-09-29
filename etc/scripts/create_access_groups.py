"""
Данные скрипт служит для создании дефолтных групп доступа:
1. админы -- все могут короли
2. ЦО -- все могут смотреть (ничего править)
3. Руководители точек -- все могут в рамках точки
4. сотрудники -- в рамках себя могут смотреть информацию

А так же создает аккаунт для админа и 2 для ЦО
"""


from uuid import uuid4
from src.apps.base.models import Group, FunctionGroup, Network
import pandas as pd


def password_generator(len=14):
    return str(uuid4()).replace('-', '')[:len]  # algo based on SHA-1 (not safe enough nowdays)


def update_group_functions(path=None, network=None, verbose=True):
    if path is None:
        path = 'etc/scripts/function_group_default.xlsx'

    if (network is None) and verbose:
        print('no network set. use None')

    df_funcs = pd.read_excel(path)

    for group_name in df_funcs['group'].unique():
        group, _group_created = Group.objects.get_or_create(name=group_name, network=network)
        fgs_created = []
        fgs_exists = []
        for _, func in df_funcs[df_funcs['group'] == group_name].iterrows():
            fg, _fg_created = FunctionGroup.objects.get_or_create(
                group=group,
                func=func['func'],
                method=func['method'],
                defaults=dict(
                    level_up=1,
                    level_down=100,
                    access_type='all',
                )
            )
            if _fg_created:
                fgs_created.append(fg)
            else:
                fgs_exists.append(fg)
        if verbose:
            print(
                f'group {"created" if _group_created else "exists"} {group.name}; perms exists: {len(fgs_exists)}, created: {len(fgs_created)}')

#
# def main(hq_accs=2):
#     """
#
#     :param hq_accs: кол-во аккаунтов для ЦО
#     :return:
#     """
#
#
#
# if __name__ == "__main__":
#     import os, django
#
#     os.environ.setdefault("DJANGO_SETTINGS_MODULE", "src.conf.djconfig")
#     django.setup()
#
#     print('start creating groups \n\n')
#     main()
#     print('\n\nfinish creating groups')

