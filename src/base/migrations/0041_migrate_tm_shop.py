from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('base', '0040_auto_20200729_1159'),
    ]

    operations = [
        migrations.RunSQL(
            "update base_shop set tm_open_list = concat('[\"',tm_shop_opens,'\"]'), tm_close_list = concat('[\"',tm_shop_closes,'\"]')"
        )]