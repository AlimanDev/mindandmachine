FROM nginx:1.19.9

COPY ./etc/compose/nginx/nginx.conf /etc/nginx/nginx.conf
RUN mkdir -p /etc/nginx/sites-enabled

COPY ./etc/compose/nginx/qos.conf /etc/nginx/sites-available/qos.conf
RUN ln -s /etc/nginx/sites-available/qos.conf /etc/nginx/sites-enabled/qos.conf

ENV TZ=Europe/Moscow
