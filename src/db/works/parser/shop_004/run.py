import os

from . import demand
from . import users
from . import queue


def run():
    path = os.path.dirname(os.path.abspath(__file__))

    users.run(path)
    demand.run(path)
    queue.run(path)
