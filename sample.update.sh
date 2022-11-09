#!/bin/bash

set -e

PROJECT_NAME=
USER=${PROJECT_NAME}
PROJECT_PATH=/var/servers/${PROJECT_NAME}/backend/qos
VENV_PATH=${PROJECT_PATH}/../env
GIT_REMOTE=origin
GIT_BRANCH=
GIT_UPSTREAM=${GIT_REMOTE}/${GIT_BRANCH}

sudo su - ${USER} -c "cd ${PROJECT_PATH} && git fetch ${GIT_REMOTE} ${GIT_BRANCH}"

LOCAL=$(cd ${PROJECT_PATH} && git rev-parse @)
REMOTE=$(cd ${PROJECT_PATH} && git rev-parse "${GIT_UPSTREAM}")
BASE=$(cd ${PROJECT_PATH} && git merge-base @ "${GIT_UPSTREAM}")

if [ $LOCAL = $REMOTE ]; then
    echo "no changes, skip updating"
elif [ $LOCAL = $BASE ]; then
    echo "start updating"

    sudo su - ${USER} -c "cd ${PROJECT_PATH} && git reset ${GIT_UPSTREAM} --hard"

    sudo su - ${USER} -c "cd ${PROJECT_PATH} && ${VENV_PATH}/bin/pip install -r requirements.txt"
    sudo su - ${USER} -c "cd ${PROJECT_PATH} && ${VENV_PATH}/bin/python manage.py migrate"

    sudo supervisorctl restart ${PROJECT_NAME}_uwsgi
    sudo supervisorctl restart ${PROJECT_NAME}_celery
    sudo supervisorctl restart ${PROJECT_NAME}_celerybeat

    echo "finish updating"
elif [ $REMOTE = $BASE ]; then
    echo "need to push"
else
    echo "diverged"
fi