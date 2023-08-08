"""Contains tests related to the utility helpers."""

from unittest import mock

from tests.base import BaseTestCase, MockResponse


class TestUtility(BaseTestCase):
    """Test utility helpers."""

    @mock.patch('utility.path')
    def test_serve_file_download(self, mock_path):
        """Test function serve_file_download."""
        from utility import serve_file_download

        response = serve_file_download('to_download', 'folder')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(1, mock_path.join.call_count)

    @mock.patch('utility.cache_has_expired', return_value=True)
    @mock.patch('flask.g.log.critical')
    @mock.patch('requests.get', return_value=MockResponse({}, 200))
    def test_get_cached_web_hook_blocks_invalid_response(self, mock_get, mock_critical, mock_is_cached_expired):
        """Test function get_cached_web_hook_blocks if GitHub response is invalid."""
        from utility import get_cached_web_hook_blocks

        cached_web_hook_blocks = get_cached_web_hook_blocks()

        mock_get.assert_called_once()
        mock_critical.assert_called_once_with("Failed to retrieve hook IP's from GitHub! API returned {}")

    @mock.patch('flask.g.log')
    @mock.patch('utility.abort')
    @mock.patch('utility.is_github_web_hook_ip', return_value=False)
    @mock.patch('utility.ip_address')
    def test_request_from_github_invalid_request(self, mock_ip_address, mock_is_github_ip, mock_abort, mock_log):
        """Test request_from_github decorator when request is invalid."""
        from utility import request_from_github

        @request_from_github()
        def example_function(*args, **kwargs):
            return "Test Success"

        response = example_function()

        mock_ip_address.assert_called_once()
        mock_is_github_ip.assert_called_once()
        self.assertEqual(mock_abort.call_count, 7)
        self.assertEqual(response, "Test Success")
