
# Задача:
# добавить в nginx перенаправление
# cоздать репу для бека и фронта (тк для каждого магаза может все отличаться), скачать с гита ветку и настроить
# создать в СУБД БД
# запустить сервер, добавить админа
# возможность тестового создавать пользователя


import os
import sys
import json
import uuid
import argparse


class ServerConfig:
    DJANGO_POSSIBLE_PIDS = list(range(8000, 8200))
    PATH_PREFIX = '/var'
    SERVERS_CONFIG_PATH = f'{PATH_PREFIX}/multi_server/multi_server/servers.json'

    def __init__(self):
        f = open(self.SERVERS_CONFIG_PATH)  # todo: add lock until process finished
        self.servers = json.load(f)
        f.close()
        self.timetable_port = '5000'

    def add_repos(self, name, self_port, db_info):
        # нужно чтобы бд c таким именем уже была
        # local config
        f = open('djconfig_local_template')
        local = f.read()
        f.close()

        # uwsgi
        f = open('uwsgi_template')
        uwsgi = f.read()
        f.close()

        curr_path = os.getcwd()
        #
        # # добавим репозитории
        os.mkdir(f'{self.PATH_PREFIX}/servers/{name}')
        # frontend
        os.mkdir(f'{self.PATH_PREFIX}/servers/{name}/frontend')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/frontend')
        os.system(f'git clone https://github.com/alexanderaleskin/QoS_frontend.git {self.PATH_PREFIX}/servers/{name}/frontend/qos')
        os.chdir(f'{self.PATH_PREFIX}/servers/{name}/frontend/qos')
        os.system(f'git checkout {name}')
        os.system("git config --global credential.helper 'cache --timeout=3600'")

        # os.system('npm install')
        # os.system('npm run build')
        os.system(f'echo "mv {self.PATH_PREFIX}/servers/{name}/frontend/qos/dist /var/www/servers/{name}/frontend/" > ../send2front.sh')
        os.chmod('../send2front.sh', 0o744)
        # os.system('../send2front.sh')

        # backend
        os.system(f'virtualenv --python=python3.6 {self.PATH_PREFIX}/servers/{name}/backend')
        os.system(f'git clone https://github.com/alexanderaleskin/QoS_backend.git {self.PATH_PREFIX}/servers/{name}/backend/qos')

        os.chdir(f'{self.PATH_PREFIX}/servers/{name}/backend/qos')
        os.system("git config --global credential.helper 'cache --timeout=3600'")
        os.system(f'git checkout {name}')
        os.system(f'../bin/pip install -r requirements.txt')

        secret = str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')

        f = open('src/conf/djconfig_local.py', 'w+')
        f.write(local % (  # старый формат форматирования (ибо { распознается для вставки
            secret,
            db_info['NAME'],
            db_info['USER'],
            db_info['PASSWORD'],
            name,
            name,
            self_port,
            self.timetable_port,
        ))
        f.close()

        os.system('../bin/python manage.py migrate')
        os.system('../bin/python manage.py collectstatic')
        # os.system(f'{self.PATH_PREFIX}/servers/{name}/backend/bin/python /var/servers/{name}/backend/qos/manage.py collectstatics')

        f = open('../uwsgi.ini', 'w+')
        f.write(uwsgi.format(
            name,
            name,
            self_port,
            name,
        ))
        f.close()

        f = open('../update_uwsgi.sh', 'w+')
        f.write(
            f'{self.PATH_PREFIX}/servers/{name}/backend/bin/uwsgi --stop /var/servers/{name}/backend/qos.pid\n'
            'sleep 2\n'
            f'{self.PATH_PREFIX}/servers/{name}/backend/bin/uwsgi --ini  /var/servers/{name}/backend/uwsgi.ini\n'
        )
        f.close()
        os.chmod('../update_uwsgi.sh', 0o744)
        os.chdir(curr_path)

        os.mkdir(f'{self.PATH_PREFIX}/log/servers/{name}')
        os.system(f'chown {name}:wfm -R {self.PATH_PREFIX}/servers/{name}')
        os.system(f'chown {name}:wfm -R {self.PATH_PREFIX}/log/servers/{name}')
        os.system(f'chown {name}:wfm -R {self.PATH_PREFIX}/www/servers/{name}')
        os.system(f'sudo -u {name} {self.PATH_PREFIX}/servers/{name}/backend/update_uwsgi.sh')
        return True

    def add_db(self, name, password):
        # print(f'sudo -u postgres psql -c "CREATE DATABASE {name} encoding \'UTF8\' LC_COLLATE = \'en_US.UTF-8\' LC_CTYPE = \'en_US.UTF-8\' TEMPLATE = template0;"')
        os.system(f'sudo -u postgres psql -c "CREATE DATABASE {name} encoding \'UTF8\' LC_COLLATE = \'en_US.UTF-8\' LC_CTYPE = \'en_US.UTF-8\' TEMPLATE = template0;"')  # aaa fucking postgres
        os.system(f'sudo -u postgres psql -c "CREATE USER {name} WITH ENCRYPTED PASSWORD \'{password}\';"')
        os.system(f'sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE {name} TO {name};"')

    def add2nginx(self, name, port):
        f = open('nginx_template')
        server_nginx = f.read()
        f.close()

        f = open(f'/etc/nginx/sites-available/{name}.conf', 'w+')
        f.write(server_nginx % (
            # name,
            name,
            name,
            name,
            port,
            port
        ))
        f.close()
        os.system(f'ln -s /etc/nginx/sites-available/{name}.conf /etc/nginx/sites-enabled/')

        os.system('service nginx restart')


    def add(self, name):
        if name in self.servers.keys():
            raise ValueError(f'{name} already exist in servers: {self.servers.keys()}')

        self_port = self.DJANGO_POSSIBLE_PIDS[0]
        while self_port in self.servers.values():
            self_port += 1

        self.servers[name] = self_port
        f = open(self.SERVERS_CONFIG_PATH, 'w+')
        json.dump(self.servers, f)
        f.close()

        os.system(f'useradd -r  {name} -g wfm')

        password_db = str(uuid.uuid4()).replace('-', '')[:14]
        print(password_db)
        db_info = {
            'NAME': name,
            'USER': name,
            'PASSWORD': password_db,
        }

        self.add_db(name, password_db)
        self.add_repos(name, self_port, db_info)
        self.add2nginx(name, self_port)



if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Add environment for client')
    parser.add_argument('name', help='Name of client')

    sc = ServerConfig()
    sc.add(parser.parse_args().name)
