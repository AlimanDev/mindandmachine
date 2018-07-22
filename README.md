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

