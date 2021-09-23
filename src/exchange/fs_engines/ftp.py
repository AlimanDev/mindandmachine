from .base import FilesystemEngine


class FtpEngine(FilesystemEngine):
    def __init__(self, host, port, username, password, **kwargs):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        super(FtpEngine, self).__init__(**kwargs)
