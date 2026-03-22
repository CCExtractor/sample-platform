"""manages configuring logging for the app."""

import logging
import logging.handlers
import os
import sys
from logging import Logger, StreamHandler
from logging.handlers import RotatingFileHandler
from typing import Optional, Union


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

        # create a file handler with permission error handling
        self._fileLogger: Optional[RotatingFileHandler] = None
        log_dir = os.path.join(folder, 'logs')
        path = os.path.join(log_dir, f'{filename}.log')

        try:
            # Ensure logs directory exists
            os.makedirs(log_dir, exist_ok=True)

            self._fileLogger = logging.handlers.RotatingFileHandler(
                path, maxBytes=1024 * 1024, backupCount=20
            )
            self._fileLogger.setLevel(logging.DEBUG)
            # create a logging format
            formatter = logging.Formatter('[%(name)s][%(levelname)s][%(asctime)s] %(message)s')
            self._fileLogger.setFormatter(formatter)
        except PermissionError as e:
            # Log file owned by different user (e.g., root vs www-data)
            # Fall back to console-only logging rather than crashing
            print(
                f"[WARNING] Cannot write to log file {path}: {e}. "
                f"Falling back to console-only logging. "
                f"Fix: sudo chown www-data:www-data {log_dir} -R",
                file=sys.stderr
            )
        except OSError as e:
            # Other filesystem errors (disk full, etc.)
            print(
                f"[WARNING] Cannot create log file {path}: {e}. "
                f"Falling back to console-only logging.",
                file=sys.stderr
            )

    @property
    def file_logger(self) -> Optional[RotatingFileHandler]:
        """
        Get file logger.

        :return: file logger or None if file logging unavailable
        :rtype: Optional[logging.handlers.RotatingFileHandler]
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
        if self._fileLogger is not None:
            logger.addHandler(self._fileLogger)
        logger.addHandler(self._consoleLogger)

        return logger
