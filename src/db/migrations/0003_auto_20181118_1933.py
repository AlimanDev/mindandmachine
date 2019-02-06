from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0002_fill_production_days_months'),
    ]

    operations = [
        migrations.CreateModel(
            name='CameraClientEvent',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('dttm', models.DateTimeField()),
                ('type', models.CharField(choices=[('T', 'toward'), ('B', 'backward')], max_length=1)),
            ],
        ),
        migrations.CreateModel(
            name='CameraClientGate',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=64)),
                ('type', models.CharField(choices=[('E', 'entry'), ('O', 'exit'), ('S', 'service')], max_length=1)),
            ],
        ),
        migrations.CreateModel(
            name='EmptyOutcomeVisitors',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], default='L', max_length=1)),
                ('value', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.CreateModel(
            name='PurchasesOutcomeVisitors',
            fields=[
                ('id', models.BigAutoField(primary_key=True, serialize=False)),
                ('dttm_forecast', models.DateTimeField()),
                ('type', models.CharField(choices=[('L', 'Long'), ('S', 'Short'), ('F', 'Fact')], default='L', max_length=1)),
                ('value', models.FloatField(default=0)),
                ('cashbox_type', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CashboxType')),
            ],
            options={
                'abstract': False,
            },
        ),
        migrations.RenameModel(
            old_name='PeriodVisitors',
            new_name='IncomeVisitors',
        ),
        migrations.AddField(
            model_name='cameraclientevent',
            name='gate',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='db.CameraClientGate'),
        ),
    ]