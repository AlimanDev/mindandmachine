# Generated by Django 3.2.9 on 2021-11-22 06:42

from django.db import migrations

def compress_info(apps, schema_editor):
    Receipt = apps.get_model('forecast', 'Receipt')
    receipts = Receipt.objects.all()
    step = 20000
    receipts_portion = receipts[:step]
    i = step
    while receipts_portion:
        Receipt.objects.bulk_update(receipts_portion, fields=['info'])
        receipts_portion = receipts[i:i + step]
        i = i + step

class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0045_alter_receipt_info'),
    ]
    atomic = False

    operations = [
        migrations.RunPython(compress_info, migrations.RunPython.noop, atomic=False),
    ]
