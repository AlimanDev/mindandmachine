# Generated by Django 2.0.5 on 2018-08-06 15:34

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('contenttypes', '0002_remove_content_type_name'),
        ('db', '0040_merge_20180805_2106'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notifications',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('was_read', models.BooleanField(default=False)),
                ('text', models.CharField(max_length=512)),
                ('type', models.CharField(choices=[('S', 'success'), ('I', 'info'), ('W', 'warning'), ('E', 'error')], default='S', max_length=1)),
                ('object_id', models.PositiveIntegerField(blank=True, null=True)),
                ('content_type', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to='contenttypes.ContentType')),
                ('to_worker', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
