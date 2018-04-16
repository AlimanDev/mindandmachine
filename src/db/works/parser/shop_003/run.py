import os
from . import users


def run():
    path = os.path.dirname(os.path.abspath(__file__))
    users.run(path)
