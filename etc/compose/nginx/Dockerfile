FROM openresty/openresty:latest

COPY ./etc/compose/nginx/nginx.conf /etc/openresty/nginx.conf
COPY ./etc/compose/nginx/qos.conf /etc/nginx/conf.d/qos.conf
COPY ./etc/compose/nginx/logrotate/nginx /etc/logrotate.d/nginx
COPY ./etc/compose/nginx/logrotate/cron /etc/crontab

ENV TZ=Europe/Moscow
