#!/bin/sh

set -e

celery -A src.adapters.celery worker -n main -P eventlet --loglevel=INFO --logfile=/webapp/logs/celery_main.log
