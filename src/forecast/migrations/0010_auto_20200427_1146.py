# Generated by Django 2.2.7 on 2020-04-27 11:46

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0009_auto_20200417_1014'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='loadtemplate',
            name='error_message',
        ),
        migrations.RemoveField(
            model_name='loadtemplate',
            name='status',
        ),
        migrations.AlterField(
            model_name='operationtypetemplate',
            name='load_template',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='operation_type_templates', to='forecast.LoadTemplate'),
        ),
    ]
