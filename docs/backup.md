# Taking backups from the server for deployment on the local machine

1. LogIn to test server:
```shell
ssh azureuser@40.118.63.212
```
> Without password. You must have public key in server.

2. Search containers with databases:
```shell
docker ps | grep postgres
```

In the list of containers you should select, what you need, for example, stage:

3. Taking backup on server from database docker container:
```shell
sudo docker exec -it dev3_postgres_1 pg_dump -U dev3 -d dev3 > backup.sql  # nahodka
sudo docker exec -it docker exec -it stage_postgres_1 pg_dump -U stage -d stage > backup.sql # stage
```
where
- `dev3_postgres_1` - docker container with database
- `-U dev3` - postgres user
- `-d dev` - name of database
- > backup.sql - stdout in file

4. After this you should download backup.sql to your locale machine:
```shell
scp azureuser@40.118.63.212:~/backup.sql ~/Downloads/backup.sql
```

5.1 If you use database on your machine, you should run sql file with backup
```shell
psql -h 127.0.0.1 -d stage -U postgres -a -f backup.sql
```
where
- `-h 127.0.0.1` - host
- `-u postgres` - run command under user postgres
- `-d stage` - name of database
- `-U postgres` - database user
- `-a` - output logs
- `-f backup.sql` - backup file

5.2 If you use postgres inside docker container, you should run sql file:
```shell
docker exec -it postgres psql -h 127.0.0.1 -d stage -U postgres -a -f backup.sql
```
where
- `docker exec -it` - run command inside docker container
- `postgres` - name of docker container with postgres
- `-h 127.0.0.1` - host
- `-u postgres` - run command under user postgres
- `-d stage` - name of database
- `-U postgres` - database user
- `-a` - output logs
- `-f backup.sql` - backup file

6. If need you can run migrations
```shell
python manage.py migrate
```