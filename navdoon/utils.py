import logging
import os


class LoggerMixIn(object):
    def __init__(self):
        self.logger = None
        self.log_pattern = "[{pid}] {message}"
        self._pid = os.getpid()

    def _log_debug(self, msg):
        self._log(msg, logging.DEBUG)

    def _log_error(self, msg):
        self._log(msg, logging.ERROR)

    def _log(self, msg, level=logging.INFO):
        if self.logger:
            self.logger.log(level,
                            self.log_pattern.format(message=msg,
                                                    pid=self._pid))
