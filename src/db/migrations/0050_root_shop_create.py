from django.db import migrations
from django.db.models import Q
def create_shop_tree(apps, schema_editor):
    Shop = apps.get_model('db', 'Shop')
    shop = Shop.objects.create(
        title='Корневой магазин',
        level=0,
        lft=0,
        rght=0,
        tree_id=0,
    )

    shops = Shop.objects.filter(
        ~Q(id = shop.id)
    ).update(parent=shop)
    Shop._tree_manager.rebuild()

class Migration(migrations.Migration):

    dependencies = [
        ('db', '0049_auto_20190826_0842'),
    ]

    operations = [
        migrations.RunPython(create_shop_tree),
    ]
