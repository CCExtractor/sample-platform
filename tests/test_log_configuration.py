import logging
import unittest
from unittest import mock

from log_configuration import LogConfiguration

# This is necessary to avoid a warning with PyCharm
# FIXME: This is apparently necessary to avoid PyCharm warnings, but mypy complains
# about assigning to a method - type: ignore seems to work but probably ignores errors
mock.patch.object = mock.patch.object  # type: ignore


class TestLogConfiguration(unittest.TestCase):
    """Test log setup."""

    def _test_init_with_log_value(self, debug, result_level):
        """Test logger initialization with specific debug and level."""
        folder = 'foo'
        filename = 'bar'
        log_dir = 'foo/logs'
        log_path = 'foo/logs/bar.log'
        console_format = '[%(levelname)s] %(message)s'
        file_format = '[%(name)s][%(levelname)s][%(asctime)s] %(message)s'
        with mock.patch('logging.handlers.RotatingFileHandler') as mock_fh:
            with mock.patch('logging.StreamHandler') as mock_sh:
                with mock.patch('logging.Formatter') as mock_formatter:
                    with mock.patch('os.path.join', side_effect=[log_dir, log_path]):
                        with mock.patch('os.makedirs') as mock_makedirs:
                            log_config = LogConfiguration(folder, filename, debug)

                            mock_makedirs.assert_called_once_with(log_dir, exist_ok=True)
                            mock_sh().setLevel.assert_called_once_with(
                                result_level)
                            mock_sh().setFormatter.assert_called_once_with(
                                mock_formatter())
                            mock_fh.assert_called_once_with(log_path,
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

    def test_init_handles_permission_error(self):
        """Test that permission errors fall back to console-only logging."""
        folder = 'foo'
        filename = 'bar'
        log_dir = 'foo/logs'
        log_path = 'foo/logs/bar.log'
        with mock.patch('logging.handlers.RotatingFileHandler') as mock_fh:
            mock_fh.side_effect = PermissionError("Permission denied")
            with mock.patch('logging.StreamHandler') as mock_sh:
                with mock.patch('os.path.join', side_effect=[log_dir, log_path]):
                    with mock.patch('os.makedirs'):
                        log_config = LogConfiguration(folder, filename, False)

                        # Console logger should still be set up
                        self.assertEqual(log_config._consoleLogger, mock_sh())
                        # File logger should be None
                        self.assertIsNone(log_config._fileLogger)
                        self.assertIsNone(log_config.file_logger)

    def test_init_handles_os_error(self):
        """Test that OSError falls back to console-only logging."""
        folder = 'foo'
        filename = 'bar'
        log_dir = 'foo/logs'
        log_path = 'foo/logs/bar.log'
        with mock.patch('logging.handlers.RotatingFileHandler') as mock_fh:
            mock_fh.side_effect = OSError("Disk full")
            with mock.patch('logging.StreamHandler') as mock_sh:
                with mock.patch('os.path.join', side_effect=[log_dir, log_path]):
                    with mock.patch('os.makedirs'):
                        log_config = LogConfiguration(folder, filename, False)

                        # Console logger should still be set up
                        self.assertEqual(log_config._consoleLogger, mock_sh())
                        # File logger should be None
                        self.assertIsNone(log_config._fileLogger)

    def test_create_logger(self):
        """Test logger creation."""
        with mock.patch.object(LogConfiguration, '__init__',
                               return_value=None):
            with mock.patch('logging.getLogger') as mock_get:
                log_config = LogConfiguration('foo', 'bar')
                log_config._fileLogger = mock.MagicMock()
                log_config._consoleLogger = mock.MagicMock()
                name = 'foobar'

                result = log_config.create_logger(name)

                mock_get.assert_called_once_with(name)
                mock_get().setLevel.assert_called_once_with(
                    logging.DEBUG)
                mock_get().addHandler.assert_has_calls([
                    mock.call(log_config._fileLogger),
                    mock.call(log_config._consoleLogger)
                ])

                self.assertEqual(result, mock_get())

    def test_create_logger_without_file_logger(self):
        """Test logger creation when file logger is unavailable."""
        with mock.patch.object(LogConfiguration, '__init__',
                               return_value=None):
            with mock.patch('logging.getLogger') as mock_get:
                log_config = LogConfiguration('foo', 'bar')
                log_config._fileLogger = None
                log_config._consoleLogger = mock.MagicMock()
                name = 'foobar'

                result = log_config.create_logger(name)

                mock_get.assert_called_once_with(name)
                mock_get().setLevel.assert_called_once_with(
                    logging.DEBUG)
                # Only console logger should be added
                mock_get().addHandler.assert_called_once_with(
                    log_config._consoleLogger)

                self.assertEqual(result, mock_get())
