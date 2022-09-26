# Taking backups from the server for deployment on the local machine

1. LogIn to test server:
```shell
ssh azureuser@40.118.63.212
```
> You must have a public key on the server in order to access it

2. Search containers with databases:
```shell
docker ps | grep postgres
```

From the list of containers you should select the one you want to take backup from, for example `stage`

3. Taking a backup from database docker container:
```shell
sudo docker exec -it dev3_postgres_1 pg_dump -U dev3 -d dev3 > backup.sql  # nahodka
sudo docker exec -it docker exec -it stage_postgres_1 pg_dump -U stage -d stage > backup.sql # stage
```
where
- `dev3_postgres_1` - targeted database docker container name
- `-U dev3` - postgres user
- `-d dev` - database name
- `backup.sql` - resulting file with the data dump that is going to be restored

4. Download generated `backup.sql` to your locale machine:
```shell
scp azureuser@40.118.63.212:~/backup.sql ~/Downloads/backup.sql
```

5.1 In case of you run Postgres on your host machine as a process, run the following backup file import:
```shell
psql -h 127.0.0.1 -d stage -U postgres -a -f backup.sql
```
where
- `-h 127.0.0.1` - target host address
- `-u postgres` - run command under user postgres
- `-d stage` - database name
- `-U postgres` - database user
- `-a` - to enable output logs
- `-f backup.sql` - backup file name, location

5.2 If you are using Postgres inside docker container, you should run the following:
```shell
docker exec -it postgres psql -h 127.0.0.1 -d stage -U postgres -a -f backup.sql
```
where
- `docker exec -it` - to run command inside docker container
- `postgres` - the name of the docker container with postgres
- `-h 127.0.0.1` - target host
- `-u postgres` - run command under user postgres
- `-d stage` - database name
- `-U postgres` - database user
- `-a` - enable output logs
- `-f backup.sql` - backup file name and location

6. Run migrations if you need it
```shell
python manage.py migrate
```