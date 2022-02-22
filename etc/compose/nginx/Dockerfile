FROM openresty/openresty:latest

RUN apt-get update && apt-get install --no-install-recommends -y \
  cron logrotate \
  && apt-get purge -y --auto-remove -o APT::AutoRemove::RecommendsImportant=false \
  && rm -rf /var/lib/apt/lists/*

COPY ./etc/compose/nginx/nginx.conf /etc/openresty/nginx.conf
COPY ./etc/compose/nginx/qos.conf /etc/nginx/conf.d/qos.conf
COPY ./etc/compose/nginx/logrotate/nginx /etc/logrotate.d/nginx
COPY ./etc/compose/nginx/logrotate/cron /cron.txt

RUN echo "" >> /cron.txt
RUN crontab /cron.txt

CMD cron && /usr/local/openresty/bin/openresty -g daemon off

ENV TZ=Europe/Moscow
