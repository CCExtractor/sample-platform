"""Contains tests related to the utility helpers."""

from unittest import mock

from tests.base import BaseTestCase


class TestUtility(BaseTestCase):
    """Test utility helpers."""

    @mock.patch('utility.path')
    def test_serve_file_download(self, mock_path):
        """Test function serve_file_download."""
        from utility import serve_file_download

        response = serve_file_download('to_download', 'folder')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(1, mock_path.join.call_count)
