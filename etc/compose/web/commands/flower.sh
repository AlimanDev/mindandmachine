#!/bin/sh

set -e

celery -A src.adapters.celery flower --conf=/webapp/flowerconfig.py
