import logging
import sys


def get_logger(name):
    logging.basicConfig(level=logging.INFO, stream=sys.stdout,
                        format="%(asctime)s [%(name)s] %(message)s")
    return logging.getLogger(name)
