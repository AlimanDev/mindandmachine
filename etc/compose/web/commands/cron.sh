#!/usr/bin/env bash

set -e

touch /webapp/logs/cron.log
echo "" >> /cron.txt
crontab /cron.txt
cron && tail -f /webapp/logs/cron.log
