#!/bin/bash

# Helper script to run all tests through Django test framework.
# Uses docker containers. Images will not be forcefully rebuilt, since `./src` directory is mounted.
# Passes all the arguments to `./manage.py test`. `--noinput` is on by default.
# To speed up testing, consider options `--parallel --keepdb`.
# To run a praticular test, pass arguments like `path.to.test` or `-k pattern`

set -e

export COMPOSE_FILE=sample.docker-compose.yml

export COMPOSE_DOCKER_CLI_BUILD=1
export DOCKER_BUILDKIT=1

docker-compose up -d web
docker-compose exec web ./manage.py test --noinput "$@"
docker-compose stop
