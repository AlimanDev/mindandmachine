#!/bin/bash
sudo su postgres -c "dropdb qos_v1 && createdb qos_v1" &&
rm -r src/db/migrations/; ./manage.py makemigrations db &&
./manage.py migrate &&
./manage.py shell -c "import src.db.debug.fill_data as m; m.load_data()" &&
./manage.py shell -c "import src.db.debug.create_superuser as m; m.create('admin', 'q@q.com', '1')"
