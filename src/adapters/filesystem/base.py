class FilesystemEngine:
    def __init__(self, base_path):
        self.base_path = base_path

    def open_file(self, filename):
        raise NotImplementedError

    def write_file(self, filename, file_obj):
        raise NotImplementedError
