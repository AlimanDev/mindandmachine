#!/bin/bash

set -e

#export REGISTRY_NAMESPACE=${REGISTRY_NAMESPACE}

#export REGISTRY_URL=
#export REGISTRY_USERNAME=
#export REGISTRY_PASSWORD=

function build_and_push() {
  docker build -t ${REGISTRY_URL}/${REGISTRY_NAMESPACE}/$1 . -f ./etc/compose/$1/Dockerfile
  docker push ${REGISTRY_URL}/${REGISTRY_NAMESPACE}/$1
}

docker login -u=${REGISTRY_USERNAME} -p=${REGISTRY_PASSWORD} ${REGISTRY_URL}

build_and_push web
build_and_push nginx
build_and_push postgres
