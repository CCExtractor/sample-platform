from unittest import mock

from tests.base import BaseTestCase


class TestProgressFTPUpload(BaseTestCase):
    """Test progress during ftp upload."""

    @mock.patch('mod_upload.controllers.upload_ftp')
    def test_process(self, mock_upload):
        """Test process method."""
        from mod_upload.progress_ftp_upload import process

        process('mock_db', 'mock_file')

        mock_upload.assert_called_once_with('mock_db', 'mock_file')
