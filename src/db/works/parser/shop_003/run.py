import os
from . import users
from . import demand


def run():
    path = os.path.dirname(os.path.abspath(__file__))
    users.run(path)
    demand.run(path)
