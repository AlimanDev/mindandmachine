#!/bin/sh

set -e

celery -A src.adapters.celery worker -n main -P eventlet --max-tasks-per-child=100 --max-memory-per-child=25000 --loglevel=INFO --logfile=/webapp/logs/celery_main.log
