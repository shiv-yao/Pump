import logging


class Observer:
    def __init__(self):
        self._logger = logging.getLogger("kronos")

    def log(self, event):
        self._logger.info("event=%s", event)
