"""manages configuring logging for the app."""

import logging
import logging.handlers
import os
from logging import Logger, StreamHandler
from logging.handlers import RotatingFileHandler
from typing import Union


class LogConfiguration:
    """handle common logging options for the entire project."""

    def __init__(self, folder: str, filename: str, debug: bool = False) -> None:
        # create console handler
        self._consoleLogger = logging.StreamHandler()
        self._consoleLogger.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
        if debug:
            self._consoleLogger.setLevel(logging.DEBUG)
        else:
            self._consoleLogger.setLevel(logging.INFO)
        # create a file handler
        path = os.path.join(folder, 'logs', f'{filename}.log')
        self._fileLogger = logging.handlers.RotatingFileHandler(path, maxBytes=1024 * 1024, backupCount=20)
        self._fileLogger.setLevel(logging.DEBUG)
        # create a logging format
        formatter = logging.Formatter('[%(name)s][%(levelname)s][%(asctime)s] %(message)s')
        self._fileLogger.setFormatter(formatter)

    @property
    def file_logger(self) -> RotatingFileHandler:
        """
        Get file logger.

        :return: file logger
        :rtype: logging.handlers.RotatingFileHandler
        """
        return self._fileLogger

    @property
    def console_logger(self) -> StreamHandler:
        """
        Get console logger.

        :return: console logger
        :rtype: logging.StreamHandler
        """
        return self._consoleLogger

    def create_logger(self, name: str) -> Logger:
        """
        Create new logger for the app.

        :param name: name for the logger
        :type name: str
        :return: logger
        :rtype: logging.Logger
        """
        logger = logging.getLogger(name)
        logger.setLevel(logging.DEBUG)
        # add the handlers to the logger
        logger.addHandler(self.file_logger)
        logger.addHandler(self.console_logger)

        return logger
