# Generated by Django 2.0.5 on 2019-08-12 07:34

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0044_shop_staff_number'),
    ]

    operations = [
        migrations.AddField(
            model_name='shop',
            name='address',
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.AddField(
            model_name='shop',
            name='code',
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='shop',
            name='dt_closed',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='shop',
            name='dt_opened',
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='shop',
            name='parent',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='db.Shop'),
        ),
        migrations.RunSQL('update db_shop set code=s.code, address=s.address, dt_opened=s.dt_opened, dt_closed=s.dt_closed from db_supershop s where db_shop.super_shop_id= s.id ;')
    ]
