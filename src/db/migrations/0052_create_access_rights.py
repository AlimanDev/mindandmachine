from django.db import migrations
from django.db.models import Q
from django.db import IntegrityError
from django.db import transaction


def change_access_rights(apps, schema_editor):
    FunctionGroup = apps.get_model('db', 'FunctionGroup')

    #SuperShops
    qs = FunctionGroup.objects.filter(
        func='add_supershop'
    ).update(func='add_department')

    qs = FunctionGroup.objects.filter(
        func='edit_supershop'
    ).update(func='edit_department')


    qs = FunctionGroup.objects.filter(
        func='get_super_shop_list'
    ).update(func='get_department_list')

    qs = FunctionGroup.objects.filter(
        func='get_supershop_stats'
    ).update(func='get_department_stats')

    qs = FunctionGroup.objects.filter(
        func='get_supershops_stats'
    ).update(func='get_department_stats_xlsx')



    qs = FunctionGroup.objects.filter(
        func='get_super_shop'
    )

    for func in qs:
        try:
            with transaction.atomic():
                func.func='get_department'
                func.save()
        except IntegrityError:
            func.delete()
    #Shops

    qs = FunctionGroup.objects.filter(
        func='add_shop'
    )
    for func in qs:
        func.func='add_department'
        try:
            with transaction.atomic():
                func.save()
        except IntegrityError:
            func.delete()

    qs = FunctionGroup.objects.filter(
        func='edit_shop'
    )
    for func in qs:
        func.func='edit_department'
        try:
            with transaction.atomic():
                func.save()
        except IntegrityError:
            func.delete()


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0051_merge_20190905_1430'),
    ]

    operations = [
        migrations.RunPython(change_access_rights),
    ]
