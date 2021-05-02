import logging
import unittest
from unittest import mock

from log_configuration import LogConfiguration

# This is necessary to avoid a warning with PyCharm
# FIXME: This is apparently necessary to avoid PyCharm warnings, but mypy complains
# about assigning to a method - type: ignore seems to work but probably ignores errors
mock.patch.object = mock.patch.object # type: ignore


class TestLogConfiguration(unittest.TestCase):
    """Test log setup."""

    def _test_init_with_log_value(self, debug, result_level):
        """Test logger initialization with specific debug and level."""
        joined_path = 'baz'
        folder = 'foo'
        filename = 'bar'
        console_format = '[%(levelname)s] %(message)s'
        file_format = '[%(name)s][%(levelname)s][%(asctime)s] %(message)s'
        with mock.patch('logging.handlers.RotatingFileHandler') as mock_fh:
            with mock.patch('logging.StreamHandler') as mock_sh:
                with mock.patch('logging.Formatter') as mock_formatter:
                    with mock.patch('os.path.join',
                                    return_value=joined_path) as mock_join:
                        log_config = LogConfiguration(folder, filename, debug)

                        mock_sh().setLevel.assert_called_once_with(
                            result_level)
                        mock_sh().setFormatter.assert_called_once_with(
                            mock_formatter())
                        mock_fh.assert_called_once_with(joined_path,
                                                        maxBytes=1024 * 1024,
                                                        backupCount=20)
                        mock_fh().setLevel.assert_called_once_with(
                            logging.DEBUG)
                        mock_fh().setFormatter.assert_called_once_with(
                            mock_formatter())
                        mock_formatter.assert_has_calls([
                            mock.call(console_format),
                            mock.call(file_format)
                        ])
                        mock_join.assert_called_once_with(folder, 'logs',
                                                          '%s.log' % filename)

                        self.assertEqual(log_config._consoleLogger, mock_sh())
                        self.assertEqual(log_config.console_logger, mock_sh())
                        self.assertEqual(log_config._fileLogger, mock_fh())
                        self.assertEqual(log_config.file_logger, mock_fh())

                        return log_config

    def test_init_correctly_initializes_the_instance_when_debug(self):
        """Test log initialization with debug mode and level."""
        self._test_init_with_log_value(True, logging.DEBUG)

    def test_init_correctly_initializes_the_instance_when_no_debug(self):
        """Test log initialization with info level."""
        self._test_init_with_log_value(False, logging.INFO)

    def test_create_logger(self):
        """Test logger creation."""
        with mock.patch.object(LogConfiguration, '__init__',
                               return_value=None):
            with mock.patch('logging.getLogger') as mock_get:
                with mock.patch.object(LogConfiguration, 'file_logger'):
                    with mock.patch.object(LogConfiguration, 'console_logger'):
                        log_config = LogConfiguration('foo', 'bar')
                        name = 'foobar'

                        result = log_config.create_logger(name)

                        mock_get.assert_called_once_with(name)
                        mock_get().setLevel.assert_called_once_with(
                            logging.DEBUG)
                        mock_get().addHandler.assert_has_calls([
                            mock.call(log_config.file_logger),
                            mock.call(log_config.console_logger)
                        ])

                        self.assertEqual(result, mock_get())
