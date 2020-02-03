from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0004_runsql'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='operationtype',
            name='name',
        ),
    ]