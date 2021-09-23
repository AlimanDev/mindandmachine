from ftplib import FTP
from io import BytesIO

from .base import FilesystemEngine


class FtpEngine(FilesystemEngine):
    def __init__(self, host, port, username, password, **kwargs):
        self.host = host
        self.port = port  # пока лишний получется...
        self.username = username
        self.password = password
        super(FtpEngine, self).__init__(**kwargs)
        self.ftp = self._init_ftp()

    def _init_ftp(self):
        ftp = FTP(host=self.host, user=self.username, passwd=self.password)
        ftp.cwd(self.base_path)
        return ftp

    def read_file(self, filename):
        r = BytesIO()
        self.ftp.retrbinary(f'RETR {filename}', r.write)
        return r.getvalue()
