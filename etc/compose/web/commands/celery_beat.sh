#!/bin/sh

set -e

celery -A src.adapters.celery beat -P gevent --scheduler django_celery_beat.schedulers:DatabaseScheduler --loglevel=INFO --logfile=/webapp/logs/celery_beat.log
