import os
import shutil

from .base import FilesystemEngine


class LocalEngine(FilesystemEngine):
    def open_file(self, filename):
        return open(os.path.join(self.base_path, filename), 'rb')

    def write_file(self, filename, file_obj):
        with open(os.path.join(self.base_path, filename), 'wb') as f:
            shutil.copyfileobj(file_obj, f, length=131072)
