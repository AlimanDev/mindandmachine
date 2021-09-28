import os

from .base import FilesystemEngine


class LocalEngine(FilesystemEngine):
    def open_file(self, filename):
        return open(os.path.join(self.base_path, filename), 'rb')
