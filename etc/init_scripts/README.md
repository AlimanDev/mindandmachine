# Инструкция к скрипту инициализации
- [Расположение](#расположение)
- [Подготовка](#подготовка)
- [Параметры скрипта](#параметры-скрипта)
- [Пример вызова скрипта](#пример-вызова-скрипта)

## Расположение
Скрипт разположен в etc/init_scripts/init_script.py

## Подготовка
Перед использованием скрипта обязательно должны быть созданы следующие директории и файлы:
- /var/servers/
- /var/www/servers/
- /var/log/servers/
- /var/log/celery/

## Параметры скрипта
- -h, \--help вывести подсказку
- \--domain STRING название поддомена \*.mindandmachine.ru (для УРВ будет urv-\*.mindandmachine.ru)
- \--back STRING ветка бэка которую необходимо развернуть **(default zoloto_prod)**
- \--lang STRING язык для развёртывания (пока что только ru и en) **(default ru)**
- \--need_test_shop BOOL нужно ли создавать тестовый отдел **(default false)**
- \--fail_remove BOOL нужно ли удалить все изменения (БД, созданные папки и файлы) в случае ошибки **(default false)**
- \--ssl_secret_path STRING путь к секретному ключу **(default /etc/MM-CERT/private.key)**
- \--ssl_public_path STRING путь к публичному ключу **(default /etc/MM-CERT/public.key)**

> Должен быть установлен и запущен **supervisor**, а также **redis-server**

## Пример вызова скрипта
> Скрипт необходимо вызвать из директории etc/init_scripts/ либо от рута либо через sudo

```bash
# python init_script.py --domain test --back test --ssl_secret_path /etc/ssl/secret.key --ssl_public_path /etc/ssl/pub.key --lang ru --fail_remove true
```
Данная команда развернёт ветку test на домене test.mindandmachine.ru. При неудаче будут удалены все созданные файлы, папки и БД относящиеся к данной операции.
Также на домене urv-test.mindandmachine.ru будет развёрнут УРВ.
Остаётся только положить фронт в папки:
- Для backend в папку /var/servers/www/{название домена у нас test}/frontend/dist/
- Для УРВ в папку /var/servers/www/{название домена у нас test}/time_attendance/frontend/
