
#!/bin/bash
source .env

docker-compose up -d --remove-orphans &&\
sleep 20 &&
sudo ip route add $ORTEKA_IP via 192.168.10.1 dev ppp0 &&
route -n | grep $ORTEKA_IP
