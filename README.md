# QoS_backend

## Installation

Using Docker and Docker-Compose:

- make sure Docker and Docker-Compose are installed
- copy `sample.docker-compose.yml` to `docker-compose.yml`
- copy `sample.local_settings_web.py` to `local_settings_web.py`. Configure as needed.
- run `docker-compose up`

That would build images for all the required by the application infrastructure and start application in development mode.

## Restoring database backup

- get a database backup (e.g. from a dev server or colleagues), copy it to `./mounts/postgres_backups/`
- run `docker-compose stop && docker-compose start postgres && docker-compose exec postgres restore file.sql.gz && docker-compose start`, replacing filename.


## Testing
Standard Django testing framework is used. Run `./test.sh`. See comments in this script for some tips.


## ---------------------------- OLD Documentation separator -----------------------------------------

## Usage

To run a dev server:

```
source venv/bin/activate
pip install -r requirements.txt
cd QoS_backend/
python manage.py runserver
```

Есть набор тестовых данных для наполнения бд и удобного отображения в интерфейсе:

```
source venv/bin/activate
python manage.py shell
from etc.scripts import fill_db_test
fill_db_test.main()
```

для создания групп доступа:
```
source venv/bin/activate
python manage.py shell
from etc.scripts import create_access_groups
create_access_groups.main()
```


## Generate doc
```
cd docs/
make html
Команда сгенерит _build/html/index.html
index.html -- это док файл
```


## Как документировать
Используем Google Style:

"""

Docstring заключается в тройные ковычки

"""

Есть список опций, которые можно использовать в docstring'e:

• Args (alias of Parameters)

• Attributes

• Example(s) (возможны оба варианта)

• Keyword Args (alias of Keyword Arguments)

• Methods

• Note(s) (возможны оба варианта)

• Other Parameters

• Parameters

• Return(s)

• Raises

• References

• See Also

• Todo

• Warning(s)

Для дополнительной информации смотри:
https://sphinxcontrib-napoleon.readthedocs.io/en/latest/example_google.html#example-google

## Структура проекта

3 основные папки в проекте:

1. base -- базовая логика интерфейса (в целом не связанная с wfm продуктом)
2. forecast -- прогнозирование нагрузки по видам работ
3. timetable -- управление графиками сотрудников

В base реализовано:
1. Поддержка ролевой модели -- через Group и FunctionGroup (для каждой функции-группы присваивается уровень доступа)
2. Иерархия отделов (Shop -- на самом деле это Department)
3. Связь сотрудника и магазина через трудоустройство (Employment)
4. Уведомления для сотрудников и возможность подписаться на них.
5. Деление магазинов по регионам/странам -- для учета специфик региона (трудового кодекса и других факторов)
6. Управление базовыми моделями


## Не работает для круглосуточных магазинов

1. celery task release_all_workers -- наверно стоит сделать через 16 часов после начала работы отпускать (больше не смогут работать)

Проблемы:

1. Для работы биржы смен необходимы права ALL на функции get_workers_to_exchange, get_cashier_timetable, get_month_stat




### что нужно делать при развертывании:

1. для создания расписания указать параметры
2. для биржи смены создать 1 модель
3. создать группы доступов и сделать юзеров для перессылки ключей

### Installation
Alternative to docker and a preferred way of configuration if you actively participate in development is to run the application using python virtual environment.

Before installing dependencies, you need to install system packages:

```shell
sudo apt-get install curl build-essential python3 python3-dev \
    python3-venv \
    graphviz \
    libgraphviz-dev \
    pkg-config \
    unixodbc-dev \
    libpq-dev \
    gettext \
    libgeos-dev \
    cron \
    logrotate \
    libpq-dev
```

Create virtual environment in your project folder use:

```shell
python3 -m venv venv
source venv/bin/activate
```
or
```shell
pip install virtualenv
virtualenv venv
source venv/bin/activate
```

Next install project dependencies:
```shell
pip install -r requirements.txt
```

*Infrastructure*

The application need to use databases postgresql and redis in work. 
These applications can be run in docker containers by commenting out services:
- web
- converter
- celery
- flower

Run all the required supporting services using docker-compose.
Please follow the steps:
```
- make sure docker, docker-compose is installed on your system
- copy `sample-docker-compose.yml` to `docker-compose.yml` file
- copy `sample.env` to `.env` file
- update `.env` file properties if needed
- run `docker-compose up` command from the terminal
```

Alternatively:

Install postgresql and redis:
```shell
sudo apt-get install postgresql redis-server
```

Run application migrations to apply DB changes:
```shell
python manage.py migrate
```

And, run the server:
```shell
python manage.py runserver
```

If you need, you can run celery:
```shell
celery -A src.celery worker -n main -l INFO
```

And flower:

```shell
celery -A src.celery flower --conf=flowerconfig.py --port=5555 
```


*Problem with version of python 3.10*

Problem 1

> import lxml.etree
> ImportError: /home/victor/projects/QoS_backend/venv/lib/python3.10/site-packages/lxml/etree.cpython-310-x86_64-linux-gnu.so: undefined symbol: _PyGen_Send

Solution:
```shell
pip install lxml --upgrade
```

Problem 2

> Encountered error while trying to install package.
> -> uwsgi

Solution:
```shell
pip install uwsgi --upgrade   # uwsgi version 2.0.20
```

Problem 3

> ImportError: cannot import name 'Mapping' from 'collections'

Solution:
```shell
pip install jinja2 tornado --upgrade
```


