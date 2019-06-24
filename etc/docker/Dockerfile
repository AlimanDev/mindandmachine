FROM python:3.6
ENV PYTHONUNBUFFERED 1
RUN mkdir /code
WORKDIR /code
ADD requirements.txt /code/
RUN apt-get update && apt-get install -y postgresql-client
RUN pip install -r requirements.txt
ADD . /code/

RUN echo 'alias manage="python manage.py"' >> ~/.bashrc

CMD bash -c "rm celerybeat.pid && python manage.py runserver 0.0.0.0:8000 & celery -A src.celery worker & celery -A src.celery beat & celery flower -A src.celery --port=5555"