class BaseImportStrategy:
    def __init__(self, fs_engine):
        self.fs_engine = fs_engine

    def execute(self):
        raise NotImplementedError
