
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
import random


class ServerConfig:
    PATH_PREFIX = '/var'

    def __init__(self):
        self.timetable_port = '5000'
        self.secret_key = str(uuid.uuid4()).replace('-', '') + str(uuid.uuid4()).replace('-', '')
        

    def remove_changes(self, name):
        os.system(f'userdel {name}')
        os.system(f'{self.PATH_PREFIX}/servers/{name}/backend/bin/uwsgi --stop /var/servers/{name}/backend/qos.pid\n')
        os.system(f'sudo -u postgres psql -c "DROP DATABASE {name};"')
        os.system(f'sudo -u postgres psql -c "DROP ROLE {name};"')
        os.system(f'rm -r {self.PATH_PREFIX}/servers/{name}')
        os.system(f'rm -r {self.PATH_PREFIX}/www/servers/{name}')
        os.system(f'rm -r {self.PATH_PREFIX}/log/servers/{name}')
        os.system(f'rm /etc/nginx/sites-available/{name}.conf')
        os.system(f'rm /etc/nginx/sites-enabled/{name}.conf')
        os.system(f'rm /etc/nginx/sites-available/{name}-urv.conf')
        os.system(f'rm /etc/nginx/sites-enabled/{name}-urv.conf')
        os.system(f'rm /etc/supervisor/conf.d/{name}_celery.conf')
        os.system(f'rm /etc/supervisor/conf.d/{name}_celerybeat.conf')
        os.system(f'rm /etc/supervisor/conf.d/{name}_uwsgi.conf')
        os.system(f'service nginx restart')
        os.system('supervisorctl update')

    def add_repos(self, name, branch, db_info):
        # нужно чтобы бд c таким именем уже была
        # local config
        with open('djconfig_local_template') as f:
            local = f.read()

        # uwsgi
        with open('uwsgi_template') as f:
            uwsgi = f.read()

        curr_path = os.getcwd()

        # # добавим репозитории
        os.mkdir(f'{self.PATH_PREFIX}/servers/{name}')
        # frontend
        os.mkdir(f'{self.PATH_PREFIX}/servers/{name}/frontend')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/frontend')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/frontend/dist')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/time_attendance')
        os.mkdir(f'{self.PATH_PREFIX}/www/servers/{name}/time_attendance/frontend') #добавить в эту папку собранный фронт urv

        os.system("git config --global credential.helper 'cache --timeout=3600'")

        # backend
        os.system(f'virtualenv --python=python3.6 {self.PATH_PREFIX}/servers/{name}/backend')
        os.system(f'git clone https://github.com/alexanderaleskin/QoS_backend.git {self.PATH_PREFIX}/servers/{name}/backend/qos')

        os.chdir(f'{self.PATH_PREFIX}/servers/{name}/backend/qos')
        os.system("git config --global credential.helper 'cache --timeout=3600'")
        os.system(f'git checkout {branch}')
        os.system(f'../bin/pip install -r requirements.txt')

        with open('src/conf/djconfig_local.py', 'w+') as f:
            f.write(local % (  # старый формат форматирования (ибо { распознается для вставки
                self.secret_key,
                db_info['NAME'],
                db_info['USER'],
                db_info['PASSWORD'],
                name,
                name,
                name,
                self.timetable_port,
            ))

        os.system('../bin/python manage.py migrate')
        os.system('../bin/python manage.py collectstatic')

        with open('../uwsgi.ini', 'w+') as f:
            f.write(uwsgi.format(
                name,
                name,
                name,
                name,
                name,
            ))

        os.chdir(curr_path)

        os.mkdir(f'{self.PATH_PREFIX}/log/servers/{name}')
        os.system(f'chown {name}:wfm -R {self.PATH_PREFIX}/servers/{name}')
        os.system(f'chown {name}:wfm -R {self.PATH_PREFIX}/log/servers/{name}')
        os.system(f'chown {name}:wfm -R {self.PATH_PREFIX}/www/servers/{name}')
        return True

    def add_db(self, name):
        os.system(f'sudo -u postgres psql -c "CREATE DATABASE {name} encoding \'UTF8\' LC_COLLATE = \'en_US.UTF-8\' LC_CTYPE = \'en_US.UTF-8\' TEMPLATE = template0;"')
        os.system(f'sudo -u postgres psql -c "CREATE USER {name} WITH PASSWORD \'{name}\';"')
        os.system(f'sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE {name} TO {name};"')

    def add2nginx(self, name, secret_path, public_path):
        with open('nginx_template') as f:
            server_nginx = f.read()

        with open(f'/etc/nginx/sites-available/{name}.conf', 'w+') as f:
            f.write(server_nginx % (
                name,
                name,
                name,
                name,
                name,
                name,
                name,
                name,
                public_path,
                secret_path,
                name,
                name,
            ))

        os.system(f'ln -s /etc/nginx/sites-available/{name}.conf /etc/nginx/sites-enabled/')
        with open('time_attendance_nginx_template') as f:
            server_nginx = f.read()

        with open(f'/etc/nginx/sites-available/{name}-urv.conf', 'w+') as f:
            f.write(server_nginx % (
                name,
                name,
                name,
                name,
                name,
                name,
                public_path,
                secret_path,
                name,
                name,
            ))

        os.system(f'ln -s /etc/nginx/sites-available/{name}-urv.conf /etc/nginx/sites-enabled/')

        os.system('service nginx restart')


    def start_celery(self, name):
        with open('celery_template') as f:
            celery_conf = f.read()

        with open('celerybeat_template') as f
            celerybeat_conf = f.read()

        with open('uwsgi_supervisor_template') as f
            uwsgi_conf = f.read()

        with open(f'/etc/supervisor/conf.d/{name}_celery.conf', 'w') as f:
            f.write(
                celery_conf % (
                    name, 
                    name,
                    name,
                    name,
                    name,
                    name,
                    name,
                )
            )
        with open(f'/etc/supervisor/conf.d/{name}_celerybeat.conf', 'w') as f:
            f.write(
                celerybeat_conf % (
                    name, 
                    name,
                    name,
                    name,
                    name,
                    name,
                )
            )

        with open(f'/etc/supervisor/conf.d/{name}_uwsgi.conf', 'w') as f:
            f.write(
                uwsgi_conf % (
                    name, 
                    name,
                    name,
                    name,
                    name,
                    name,
                    name,
                )
            )

        os.system('supervisorctl update')
        os.system(f'supervisorctl start {name}_celery {name}_celerybeat {name}_uwsgi')


    def add(self, name, back_branch, secret_path, public_path):
        if os.path.isdir(f'{self.PATH_PREFIX}/servers/{name}'):
            answer = input('Project already exists! Remove? y/N')
            if answer == 'y':
                a = random.randint(0, 100)
                b = random.randint(0, 100)
                c = a + b
                user_c = input(f'Are you sure? Solve this: {a} + {b} = ?')
                if int(user_c) == c:
                    self.remove_changes(name)

        os.system(f'useradd -r  {name} -g wfm')

        db_info = {
            'NAME': name,
            'USER': name,
            'PASSWORD': name,
        }

        self.add_db(name)
        self.add_repos(name, back_branch, db_info)
        self.add2nginx(name, secret_path, public_path)
        self.start_celery(name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Add environment for client')
    parser.add_argument('--domain', help='Domain name of client', required=True)
    parser.add_argument('--back', help='Backend branch', default='zoloto_prod')
    parser.add_argument('--lang', help='Language of client', default='ru')
    parser.add_argument('--fail_remove', help='Remove all changes if process fails', type=bool, default=False)
    parser.add_argument('--ssl_secret_path', help='Path to secret key', default='/etc/MM-CERT/private.key', type=str)
    parser.add_argument('--ssl_public_path', help='Path to public key', default='/etc/MM-CERT/public.key', type=str)
    parser.add_argument('--need_test_shop', help='Creates test shop', default=False, type=bool)



    args = parser.parse_args()
    sc = ServerConfig()
    try:
        sc.add(args.domain, args.back, args.ssl_secret_path, args.ssl_public_path)
        os.chdir(f'{sc.PATH_PREFIX}/servers/{args.domain}/backend/qos/etc/init_scripts/')
        #call fill db
        res = os.system(f'../../../bin/python init_db.py --lang {args.lang} --need_test_shop {args.need_test_shop}')
        if res != 0:
            raise Exception('Error in fill_db')
    except Exception as e:
        print("-------------ERROR-------------")
        print(e)
        print("-------------------------------")
        if (args.fail_remove):
            print('removing changes...')
            sc.remove_changes(args.domain)
