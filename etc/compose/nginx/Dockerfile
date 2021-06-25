FROM openresty/openresty:latest

COPY ./etc/compose/nginx/nginx.conf /etc/openresty/nginx.conf
COPY ./etc/compose/nginx/qos.conf /etc/nginx/conf.d/qos.conf

ENV TZ=Europe/Moscow
