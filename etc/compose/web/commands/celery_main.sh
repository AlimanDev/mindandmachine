#!/bin/sh

set -e

celery -A src.adapters.celery worker -n main -P gevent --loglevel=INFO --logfile=/webapp/logs/celery_main.log
