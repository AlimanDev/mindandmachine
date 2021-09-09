# Generated by Django 2.2.16 on 2021-08-09 06:15

from django.db import migrations, models
from django.conf import settings
import django.db.models.deletion


def migrate_att_area(apps, schema_editor):
    if settings.ZKTECO_INTEGRATION:
        from src.integration.tasks import sync_att_area_zkteco
        sync_att_area_zkteco()
        ShopExternalCode = apps.get_model('integration', 'ShopExternalCode')
        AttendanceArea = apps.get_model('integration', 'AttendanceArea')
        areas = {}
        for att_area in AttendanceArea.objects.all():
            areas[att_area.code] = att_area
        for shop_token in ShopExternalCode.objects.all():
            area = areas.get(shop_token.code)
            if not area:
                shop_token.delete()
                continue
            shop_token.attendance_area = area
            shop_token.save()

class Migration(migrations.Migration):

    dependencies = [
        ('integration', '0006_merge_20210616_0748'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceArea',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=128, verbose_name='Имя')),
                ('code', models.CharField(blank=True, max_length=64, null=True, verbose_name='Код')),
                ('external_system', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='integration.ExternalSystem')),
            ],
            options={
                'verbose_name': 'Зона учета внешней системы',
                'verbose_name_plural': 'Зоны учета внешней системы',
            },
        ),
        migrations.AddField(
            model_name='shopexternalcode',
            name='attendance_area',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, to='integration.AttendanceArea'),
        ),
        migrations.RunPython(migrate_att_area),
        migrations.RemoveField(
            model_name='shopexternalcode',
            name='code',
        ),
        migrations.RemoveField(
            model_name='shopexternalcode',
            name='external_system',
        ),
        migrations.AlterField(
            model_name='shopexternalcode',
            name='attendance_area',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='integration.AttendanceArea'),
        ),
    ]
