from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('forecast', '0003_migrate_operationtypename'),
    ]

    operations = [
        migrations.RunSQL(
            'update forecast_operationtype as o set operation_type_name_id =  n.id from forecast_operationtypename n where o.name=n.name'),
    ]
