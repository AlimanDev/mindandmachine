# Команды для развертывание дев с docker

dev:
	cp ./requirements.txt ./etc/docker/requirements.txt
	docker-compose -f etc/docker/docker-compose.yml up

stop:
	docker-compose -f etc/docker/docker-compose.yml stop

ssh-web:
	docker-compose -f etc/docker/docker-compose.yml exec web bash

ssh-db:
	docker-compose -f etc/docker/docker-compose.yml exec db bash

build:
	cp ./requirements.txt ./etc/docker/requirements.txt
	docker-compose -f etc/docker/docker-compose.yml build

reload:
	docker-compose -f etc/docker/docker-compose.yml restart web