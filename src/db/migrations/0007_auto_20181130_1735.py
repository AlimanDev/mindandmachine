from django.db import migrations, models

class Migration(migrations.Migration):

    dependencies = [
        ('db', '0006_merge_20181123_0934'),
    ]

    operations = [
        migrations.AlterField(
            model_name='cashboxtype',
            name='period_demand_params',
            field=models.CharField(default='{"max_depth": 10, "eta": 0.2, "min_split_loss": 200, "reg_lambda": 2, "silent": 1}', max_length=1024),
        ),
    ]