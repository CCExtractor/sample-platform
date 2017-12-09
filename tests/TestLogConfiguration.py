import logging
import unittest

from mock import mock

from log_configuration import LogConfiguration

mock.patch.object = mock.patch.object  # This is necessary to avoid a warning with PyCharm


class TestLogConfiguration(unittest.TestCase):
    def _test_init_with_log_value(self, debug, result_level):
        with mock.patch('logging.StreamHandler') as mock_stream_handler:
            with mock.patch('logging.Formatter') as mock_formatter:
                with mock.patch('logging.handlers.RotatingFileHandler') as mock_file_handler:
                    joined_path = 'baz'
                    with mock.patch('os.path.join', return_value=joined_path) as mock_join:
                        folder = 'foo'
                        filename = 'bar'

                        log_config = LogConfiguration(folder, filename, debug)

                        mock_stream_handler().setLevel.assert_called_once_with(result_level)
                        mock_stream_handler().setFormatter.assert_called_once_with(mock_formatter())
                        mock_file_handler.assert_called_once_with(joined_path, maxBytes=1024 * 1024, backupCount=20)
                        mock_file_handler().setLevel.assert_called_once_with(logging.DEBUG)
                        mock_file_handler().setFormatter.assert_called_once_with(mock_formatter())
                        mock_formatter.assert_has_calls([
                            mock.call('[%(levelname)s] %(message)s'),
                            mock.call('[%(name)s][%(levelname)s][%(asctime)s] %(message)s')
                        ])
                        mock_join.assert_called_once_with(folder, 'logs', '%s.log' % filename)

                        self.assertEqual(log_config._consoleLogger, mock_stream_handler())
                        self.assertEqual(log_config.console_logger, mock_stream_handler())
                        self.assertEqual(log_config._fileLogger, mock_file_handler())
                        self.assertEqual(log_config.file_logger, mock_file_handler())

                        return log_config

    def test_init_correctly_initializes_the_instance_when_debug(self):
        self._test_init_with_log_value(True, logging.DEBUG)

    def test_init_correctly_initializes_the_instance_when_no_debug(self):
        self._test_init_with_log_value(False, logging.INFO)

    def test_create_logger(self):
        with mock.patch('logging.getLogger') as mock_get:
            with mock.patch.object(LogConfiguration, '__init__', return_value=None):
                with mock.patch.object(LogConfiguration, 'file_logger'):
                    with mock.patch.object(LogConfiguration, 'console_logger'):
                        log_config = LogConfiguration('foo', 'bar')
                        name = 'foobar'

                        result = log_config.create_logger(name)

                        mock_get.assert_called_once_with(name)
                        mock_get().setLevel.assert_called_once_with(logging.DEBUG)
                        mock_get().addHandler.assert_has_calls([
                            mock.call(log_config.file_logger),
                            mock.call(log_config.console_logger)
                        ])

                        self.assertEqual(result, mock_get())
