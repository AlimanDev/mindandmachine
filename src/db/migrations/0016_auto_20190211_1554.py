# Generated by Django 2.0.5 on 2019-02-11 15:54

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0015_auto_20190206_1432'),
    ]

    operations = [
        migrations.CreateModel(
            name='FunctionGroup',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_modified', models.DateTimeField(blank=True, null=True)),
                ('func', models.CharField(choices=[('get_cashboxes', 'get_cashboxes'), ('get_types', 'get_types')], max_length=128)),
                ('access_type', models.CharField(choices=[('S', 'self'), ('TS', 'shop'), ('TSS', 'supershop'), ('A', 'all')], max_length=32)),
            ],
        ),
        migrations.CreateModel(
            name='Group',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm_added', models.DateTimeField(auto_now_add=True)),
                ('dttm_modified', models.DateTimeField(blank=True, null=True)),
                ('name', models.CharField(max_length=128)),
                ('subordinates', models.ManyToManyField(blank=True, related_name='_group_subordinates_+', to='db.Group')),
            ],
        ),
        migrations.AddField(
            model_name='functiongroup',
            name='group',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.Group'),
        ),
    ]
