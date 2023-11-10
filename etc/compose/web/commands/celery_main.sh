#!/bin/sh

set -e

celery -A src.adapters.celery worker -n main -P eventlet --concurrency=100 --loglevel=INFO --logfile=/webapp/logs/celery_main.log
