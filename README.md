# QoS_backend

## Installation

```
pip install virtualenv
virtualenv venv
```

## Usage

To run a dev server:

```
source venv/bin/activate
pip install -r requirements.txt
cd QoS_backend/
python manage.py runserver
```

## Generate doc
```
cd docs/
make html
Команда сгенерит _build/html/index.html
index.html -- это док файл
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

