import os
import tempfile
from unittest.mock import MagicMock, patch

from mod_api.services.storage import (get_log_file_path,
                                      get_test_results_base_path,
                                      resolve_artifact)
from tests.base import BaseTestCase


class TestServicesStorage(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.test_dir = tempfile.TemporaryDirectory()
        self.dir_path = self.test_dir.name

    def tearDown(self):
        self.test_dir.cleanup()
        super().tearDown()

    def create_file(self, relative_path):
        full_path = os.path.join(self.dir_path, relative_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, 'w') as f:
            f.write('dummy content')
        return full_path

    def mock_config_get(self, key, default=None):
        if key == 'SAMPLE_REPOSITORY':
            return self.dir_path
        if key == 'GCS_SIGNED_URL_EXPIRY_LIMIT':
            return 60
        return default

    @patch('run.config')
    @patch('run.storage_client_bucket')
    def test_resolve_artifact_both_exist(self, mock_bucket, mock_config):
        mock_config.get.side_effect = self.mock_config_get
        self.create_file('test_artifact.txt')

        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = 'https://signed.url'
        mock_bucket.blob.return_value = mock_blob

        url, status = resolve_artifact('test_artifact.txt')
        self.assertEqual(url, 'https://signed.url')
        self.assertEqual(status, 'ok')
        mock_blob.generate_signed_url.assert_called_once()

    @patch('run.config')
    @patch('run.storage_client_bucket')
    def test_resolve_artifact_only_gcs(self, mock_bucket, mock_config):
        mock_config.get.side_effect = self.mock_config_get

        mock_blob = MagicMock()
        mock_blob.exists.return_value = True
        mock_blob.generate_signed_url.return_value = 'https://signed.url'
        mock_bucket.blob.return_value = mock_blob

        url, status = resolve_artifact('test_artifact.txt')
        self.assertEqual(url, 'https://signed.url')
        self.assertEqual(status, 'degraded')

    @patch('run.config')
    @patch('run.storage_client_bucket')
    def test_resolve_artifact_gcs_blob_no_exists_check(self, mock_bucket, mock_config):
        mock_config.get.side_effect = self.mock_config_get
        self.create_file('test_artifact.txt')

        mock_blob = MagicMock()
        mock_blob.generate_signed_url.return_value = 'https://signed.url'
        mock_bucket.blob.return_value = mock_blob

        resolve_artifact('test_artifact.txt')
        mock_blob.exists.assert_not_called()

    @patch('run.config')
    @patch('run.storage_client_bucket', new=None)
    def test_resolve_artifact_only_local(self, mock_config):
        mock_config.get.side_effect = self.mock_config_get
        self.create_file('test_artifact.txt')

        url, status = resolve_artifact('test_artifact.txt')
        self.assertIsNone(url)
        self.assertEqual(status, 'degraded')

    @patch('run.config')
    @patch('run.storage_client_bucket', new=None)
    def test_resolve_artifact_missing(self, mock_config):
        mock_config.get.side_effect = self.mock_config_get

        url, status = resolve_artifact('test_artifact.txt')
        self.assertIsNone(url)
        self.assertEqual(status, 'missing')

    @patch('run.config')
    @patch('run.storage_client_bucket')
    def test_resolve_artifact_gcs_exception(self, mock_bucket, mock_config):
        mock_config.get.side_effect = self.mock_config_get
        self.create_file('test_artifact.txt')

        mock_bucket.blob.side_effect = Exception("GCS Error")

        url, status = resolve_artifact('test_artifact.txt')
        self.assertIsNone(url)
        self.assertEqual(status, 'degraded')

    @patch('run.config')
    def test_get_log_file_path_exists(self, mock_config):
        mock_config.get.side_effect = self.mock_config_get
        path = self.create_file('LogFiles/123.txt')

        result = get_log_file_path(123)
        self.assertEqual(os.path.normpath(result), os.path.normpath(path))

    @patch('run.config')
    def test_get_log_file_path_missing(self, mock_config):
        mock_config.get.side_effect = self.mock_config_get

        result = get_log_file_path(123)
        self.assertIsNone(result)

    @patch('run.config')
    def test_get_test_results_base_path(self, mock_config):
        mock_config.get.return_value = '/fake/repo'

        result = get_test_results_base_path()
        expected = os.path.join('/fake/repo', 'TestResults')
        self.assertEqual(result, expected)
