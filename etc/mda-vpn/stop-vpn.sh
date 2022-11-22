#!/bin/bash
source .env

sudo ip route del $ORTEKA_IP via 192.168.10.1 dev ppp0 &&
docker-compose stop &&
route -n | grep $ORTEKA_IP
