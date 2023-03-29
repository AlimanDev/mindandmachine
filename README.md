# QoS_backend

## Installation

Using Docker and Docker Compose:

- make sure Docker and Docker Compose are installed
- copy `sample.docker-compose.yml` to `docker-compose.yml`
- run `docker compose up`

That would build images for all the required by the application infrastructure and start application in development mode.
Source code in development is usually mounted through volume, so you don't need to rebuild each time.

## Restoring database backup

- get a database backup (e.g. from a dev server or colleagues), copy it to `./mounts/postgres_backups/`
- run `docker compose stop && docker compose start postgres && docker compose exec postgres restore file.sql.gz && docker compose start`, replacing filename.

## Testing

Standard Django testing framework is used. Run `./test.sh`. See comments in this script for some tips.
Alternatively, run `docker compose exec web ./manage.py test`

## Migrations

`docker-compose exec web ./manage.py makemigrations`
Migrate command is hardcoded in `./etc/compose/web/commands/web.sh`

## Translations i18n

- `docker-compose exec web ./manage.py makemessages --locale=ru -d django`
- Translate as needed in `data/locale/ru/LC_MESSAGES/django.po`
- `docker-compose exec web ./manage.py compilemessages --locale=ru`

## Django shell
`docker-compose exec web ./manage.py shell`
