# Generated by Django 2.0.5 on 2018-11-20 11:51

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0003_auto_20181118_1933'),
    ]

    operations = [
        migrations.CreateModel(
            name='AttendanceRecords',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm', models.DateTimeField()),
                ('type', models.CharField(choices=[('C', 'coming'), ('L', 'leaving'), ('S', 'break start'), ('E', 'break_end')], max_length=1)),
                ('worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
