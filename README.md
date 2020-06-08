# QoS_backend

## Installation

```
pip install virtualenv
virtualenv venv
```

Или используя Docker:
```bash
./make dev
```

Эта команда поднимает python, postgres, redis в контейнерах докера и запустит проект в дев режиме.

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


Для запуска всех тестов:
```
./manage.py test 
```
Для запуска определенных тестов необходимо указывать путь, например:
```
./manage.py test src.main.demand.tests
./manage.py test src.main.tablet.tests.TestTablet.test_get_cashiers_info
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

