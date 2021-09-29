import tempfile
from ftplib import FTP

from django.conf import settings

from src.base.exceptions import EnvLvlViolation
from .base import FilesystemEngine


class FtpEngine(FilesystemEngine):
    def __init__(self, host, port, username, password, **kwargs):
        self.host = host
        self.port = port  # пока лишний получется...
        self.username = username
        self.password = password
        super(FtpEngine, self).__init__(**kwargs)
        self.ftp = self._init_ftp()

    def _init_ftp(self):  # TODO: нужно ли закрывать коннекшн?
        ftp = FTP(host=self.host, user=self.username, passwd=self.password)
        ftp.cwd(self.base_path)
        return ftp

    def open_file(self, filename):
        tmp_f = tempfile.NamedTemporaryFile(mode='wb+')
        self.ftp.retrbinary(f'RETR {filename}', tmp_f.write)
        tmp_f.seek(0)
        return tmp_f

    def write_file(self, filename, file_obj):
        if not settings.ENV_LVL == settings.ENV_LVL_PROD:
            raise EnvLvlViolation()
        self.ftp.storbinary(f'STOR {filename}', file_obj)
