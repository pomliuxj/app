import time
import logging
LOGGINGS=logging.getLogger('loggers')
from django.db import connections


def clock(func):
    def clocked(*args):
        t1 = time.perf_counter()
        result = func(*args)
        t2 = time.perf_counter() - t1
        name = func.__name__
        args_str = ', '.join(repr(arg) for arg in args)
        LOGGINGS.info(f'Loging_Info************* {t2}  args:({name}:{args_str}) ->:{result} ')
        return result

    return clocked



def close_old_connections():
    for conn in connections.all():
        conn.close_if_unusable_or_obsolete()

def handle_db_connections(func):
    def func_wrapper(*args):
        close_old_connections()
        result = func(*args)
        close_old_connections()
        return result
    return func_wrapper
