#!/bin/bash
sudo su postgres -c "dropdb qos_v1 && createdb qos_v1" &&
./manage.py migrate &&
./manage.py fill_db &&
echo 'SUCCESS';

echo 'FINISHED'
