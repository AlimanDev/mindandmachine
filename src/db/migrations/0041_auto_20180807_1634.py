# Generated by Django 2.0.5 on 2018-08-07 16:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0040_merge_20180805_2106'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='user',
            name='permissions',
        ),
        migrations.AddField(
            model_name='user',
            name='group',
            field=models.CharField(choices=[('C', 'cashiers'), ('M', 'manager'), ('S', 'supervisor'), ('D', 'director'), ('H', 'headquarter')], default='C', max_length=1),
        ),
    ]
