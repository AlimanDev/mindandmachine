#!/bin/bash

set -e

export COMPOSE_FILE=docker-compose-tests.yml
#export COMPOSE_PROJECT_NAME=qos_tests

export COMPOSE_DOCKER_CLI_BUILD=1
export DOCKER_BUILDKIT=1

docker-compose down --remove-orphans
#docker-compose build postgres
docker-compose build web

if [ ${1:-'foo'} = 'with_coverage' ]; then
    docker-compose run web pytest -v \
      --junitxml=./etc/reports/junit.xml \
      --ignore=src/main \
      && coverage xml -o ./etc/reports/coverage.xml
else
    docker-compose run web pytest -v \
      --junitxml=./etc/reports/junit.xml \
      --no-cov \
      --ignore=src/main \
      --exitfirst
fi

docker-compose down --remove-orphans
