class FilesystemEngine:
    def __init__(self, base_path):
        self.base_path = base_path

    def ls(self):
        raise NotImplementedError

    def ls_tree(self):  # ннада ???
        raise NotImplementedError

    def cd(self, path):
        raise NotImplementedError

    def read_file(self, filename):
        raise NotImplementedError

    def write_file(self, path, content):
        raise NotImplementedError

    def mkdir(self, path):
        raise NotImplementedError
