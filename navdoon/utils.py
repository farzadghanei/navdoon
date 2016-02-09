import logging


class LoggerMixIn(object):
    def __init__(self):
        self.logger = None

    def _log(self, message, level=logging.INFO):
        logger = self.logger
        if logger:
            logger._log(level, message)