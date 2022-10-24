import io
from pathlib import Path
from typing import Union
from django.core.files import File


def save_on_server(contents: Union[io.BytesIO, str], filename: str, directory: Union[str, Path], serve_url: Union[str, None] = None) -> File:
    """
    Save a file on server's hard drive.
    The directory and parents will be created, if they don't exist already.
    If serve_url is provided, the `File` instance will have an `url` attribute (`serve_url + filename`), at which the file is served.
    Please consider the cleanup mechanism when saving anything on the hard drive.
    """
    directory = Path(directory)
    directory.mkdir(exist_ok=True, parents=True)
    full_path = directory / filename
    mode = 'wb' if isinstance(contents, bytes) else 'w'
    with open(full_path, mode) as f:
        f.write(contents)
        file = File(f)

    if serve_url:
        file.url = serve_url + filename

    return file
