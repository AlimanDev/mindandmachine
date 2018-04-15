#!/bin/bash
sudo su postgres -c "dropdb qos_v1 && createdb qos_v1" &&
rm -r src/db/migrations/; ./manage.py makemigrations db &&
./manage.py migrate &&
./manage.py fill_db
