#!/bin/sh

set -e

celery -A src.celery worker -n main --loglevel=INFO --logfile=/webapp/logs/celery_main.log
