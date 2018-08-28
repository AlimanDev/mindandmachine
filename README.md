# QoS_backend

## Installation

```
pip install pipenv
pipenv install
```

## Usage

To run a dev server:

```
pipenv shell
python manage.py runserver
```

Для запуска всех тестов:
```
./manage.py test 
```
Для запуска определенных тестов необходимо указывать путь, например:
```
./manage.py test src.main.demand.tests
./manage.py test src.main.tablet.tests.TestTablet.test_get_cashiers_info
```


## Структура проекта

Нестандартное расположение файлов для джанго. Основной код находиться в src, где следующие подпапки:

- conf -- файлы конфигурации сервера
- db -- файлы для работы с СУБД:
  - models.py -- все модели описаны в этом одном файле
  - works -- папки с данными для тестовых данных и выгрузки их, инициализации 
- main -- основной код и вьюхи для страниц, функции разделены по страницам приложения, где они используются
- management -- команды для manage.py:
  - ./manage.py fill_db -- заполняем СУБД данными тестовыми
- util -- полезные функции, в том числе декоратор api_method

Более подробная информации в вики https://github.com/alexanderaleskin/QoS_backend/wiki



## Не работает для круглосуточных магазинов

1. celery task release_all_workers -- наверно стоит сделать через 16 часов после начала работы отпускать (больше не смогут работать)
2. алгоритм воообще не знает как по ночам делать -- надо менять структуру
3. надо бы поменять time на datetime (или combine?)

