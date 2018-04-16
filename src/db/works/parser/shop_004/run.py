from . import demand
from . import users
from . import queue


def run():
    users.run()
    demand.run()
    queue.run()
