from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('db', '0007_auto_20181130_1735'),
    ]

    operations = [
        migrations.AddField(
            model_name='cashboxtype',
            name='period_queue_params',
            field=models.CharField(default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 1, "reg_lambda": 0.1, "silent": 1, "iterations": 20}', max_length=1024),
        ),
        migrations.AlterField(
            model_name='cashboxtype',
            name='period_demand_params',
            field=models.CharField(default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 200, "reg_lambda": 2, "silent": 1, "iterations": 20}', max_length=1024),
        ),
    ]