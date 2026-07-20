import os
import tempfile
from unittest.mock import patch

from mod_api.services.log_service import (_extract_level, _extract_source,
                                          _matches_level, read_log_lines)
from tests.api.base import ApiTestCase


class TestServicesLogService(ApiTestCase):
    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()
        super().tearDown()

    def create_log_file(self, content, encoding='utf-8'):
        path = os.path.join(self.dir_path, "1.txt")
        with open(path, 'w', encoding=encoding, newline='') as f:
            f.write(content)
        return path

    @patch('mod_api.services.log_service.get_log_file_path')
    def test_read_log_lines_not_found(self, mock_get_path):
        mock_get_path.return_value = None
        with self.assertRaises(FileNotFoundError):
            read_log_lines(1)

    @patch('mod_api.services.log_service.get_log_file_path')
    def test_read_log_lines_basic(self, mock_get_path):
        content = "INFO worker: Starting\nDEBUG worker: Doing stuff\nERROR build: Failed\n"
        path = self.create_log_file(content)
        mock_get_path.return_value = path

        lines, next_cursor = read_log_lines(1)
        self.assertEqual(len(lines), 3)
        self.assertIsNone(next_cursor)
        self.assertEqual(lines[0]['level'], 'info')
        self.assertEqual(lines[0]['source'], 'worker')
        self.assertEqual(lines[0]['message'], "INFO worker: Starting")
        self.assertEqual(lines[2]['level'], 'error')
        self.assertEqual(lines[2]['source'], 'build')

    @patch('mod_api.services.log_service.get_log_file_path')
    def test_read_log_lines_pagination(self, mock_get_path):
        content = "Line 1\nLine 2\nLine 3\nLine 4\n"
        path = self.create_log_file(content)
        mock_get_path.return_value = path

        lines, next_cursor = read_log_lines(1, limit=2)
        self.assertEqual(len(lines), 2)
        self.assertEqual(next_cursor, '2')
        self.assertEqual(lines[0]['message'], "Line 1")
        self.assertEqual(lines[1]['message'], "Line 2")

        lines, next_cursor = read_log_lines(1, cursor=next_cursor, limit=2)
        self.assertEqual(len(lines), 2)
        self.assertIsNone(next_cursor)
        self.assertEqual(lines[0]['message'], "Line 3")
        self.assertEqual(lines[1]['message'], "Line 4")

    @patch('mod_api.services.log_service.get_log_file_path')
    def test_read_log_lines_limit_clamped(self, mock_get_path):
        content = "Line\n" * 1500
        path = self.create_log_file(content)
        mock_get_path.return_value = path

        lines, _ = read_log_lines(1, limit=2000)
        # Should be clamped to 500
        self.assertEqual(len(lines), 500)

    @patch('mod_api.services.log_service.get_log_file_path')
    def test_read_log_lines_filters(self, mock_get_path):
        content = "INFO worker: Starting\nDEBUG build: Doing stuff\nERROR build: Failed\n"
        path = self.create_log_file(content)
        mock_get_path.return_value = path

        # Filter by level
        lines, _ = read_log_lines(1, level='error')
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]['message'], "ERROR build: Failed")

        # Filter by source
        lines, _ = read_log_lines(1, source='build')
        self.assertEqual(len(lines), 2)

        # Filter by contains
        lines, _ = read_log_lines(1, contains='STARTING')
        self.assertEqual(len(lines), 1)

    @patch('mod_api.services.log_service.get_log_file_path')
    def test_read_log_lines_cp1252(self, mock_get_path):
        path = os.path.join(self.dir_path, "1.txt")
        with open(path, 'wb') as f:
            f.write(b"INFO \x80 error\n")  # cp1252 euro sign
        mock_get_path.return_value = path

        lines, _ = read_log_lines(1)
        self.assertEqual(len(lines), 1)
        self.assertIn("\u20ac", lines[0]['message'])

    def test_extract_level(self):
        self.assertEqual(_extract_level("A CRITICAL error"), "critical")
        self.assertEqual(_extract_level("Some ERROR occurred"), "error")
        self.assertEqual(_extract_level("This is a WARNING"), "warning")
        self.assertEqual(_extract_level("Just INFO"), "info")
        self.assertEqual(_extract_level("DEBUG logging"), "debug")
        self.assertEqual(_extract_level("Unknown format"), "info")  # default

    def test_extract_source(self):
        self.assertEqual(_extract_source(
            "orchestrator doing something"), "orchestrator")
        self.assertEqual(_extract_source("worker executing"), "worker")
        self.assertEqual(_extract_source("build failed"), "build")
        self.assertEqual(_extract_source("test_runner passed"), "test_runner")
        self.assertEqual(_extract_source("web request"), "web")
        self.assertEqual(_extract_source("unknown source"), "web")  # default

    def test_matches_level(self):
        self.assertTrue(_matches_level("ERROR", "error"))
        self.assertFalse(_matches_level("INFO", "error"))
