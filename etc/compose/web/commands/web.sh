#!/bin/sh

set -e

python manage.py migrate --noinput
python manage.py collectstatic --noinput

# TODO: добавить возможность настройки конфига с помощью переменный окружения
uwsgi --ini uwsgi.ini
