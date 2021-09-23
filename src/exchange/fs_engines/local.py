import os

from .base import FilesystemEngine


class LocalEngine(FilesystemEngine):
    def read_file(self, filename):
        with open(os.path.join(self.base_path, filename), 'rb') as f:
            return f.read()
