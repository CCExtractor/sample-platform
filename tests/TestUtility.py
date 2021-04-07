"""Contains tests related to the utility helpers."""

from unittest import mock

from tests.base import BaseTestCase


class TestUtility(BaseTestCase):
    """Test c"""

    @mock.patch('utility.path')
    def test_serve_file_download(self, mock_path):
        """Test function serve_file_download."""
        from utility import serve_file_download

        response = serve_file_download('to_download', 'folder', 'accl_folder')

        self.assert200(response)
        self.assertEqual(2, mock_path.join.call_count)
        mock_path.getsize.assert_called_once_with(mock_path.join())
