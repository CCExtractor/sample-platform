"""Tests for the health check endpoints."""

import json
from unittest import mock

from tests.base import BaseTestCase


class TestHealthEndpoints(BaseTestCase):
    """Test health check endpoints."""

    @mock.patch('mod_health.controllers.check_config')
    @mock.patch('mod_health.controllers.check_database')
    def test_health_endpoint_returns_200_when_healthy(self, mock_db, mock_config):
        """Test that /health returns 200 when all checks pass."""
        mock_db.return_value = {'status': 'ok'}
        mock_config.return_value = {'status': 'ok'}

        response = self.app.test_client().get('/health')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('timestamp', data)
        self.assertIn('checks', data)
        self.assertEqual(data['checks']['database']['status'], 'ok')
        self.assertEqual(data['checks']['config']['status'], 'ok')

    @mock.patch('mod_health.controllers.check_config')
    @mock.patch('mod_health.controllers.check_database')
    def test_health_endpoint_returns_503_when_database_fails(self, mock_db, mock_config):
        """Test that /health returns 503 when database check fails."""
        mock_db.return_value = {'status': 'error', 'message': 'Connection failed'}
        mock_config.return_value = {'status': 'ok'}

        response = self.app.test_client().get('/health')
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'unhealthy')
        self.assertEqual(data['checks']['database']['status'], 'error')

    @mock.patch('mod_health.controllers.check_config')
    @mock.patch('mod_health.controllers.check_database')
    def test_health_endpoint_returns_503_when_config_fails(self, mock_db, mock_config):
        """Test that /health returns 503 when config check fails."""
        mock_db.return_value = {'status': 'ok'}
        mock_config.return_value = {'status': 'error', 'message': 'Missing keys'}

        response = self.app.test_client().get('/health')
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'unhealthy')
        self.assertEqual(data['checks']['config']['status'], 'error')

    def test_liveness_endpoint_returns_200(self):
        """Test that /health/live always returns 200."""
        response = self.app.test_client().get('/health/live')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'alive')
        self.assertIn('timestamp', data)

    @mock.patch('mod_health.controllers.check_config')
    @mock.patch('mod_health.controllers.check_database')
    def test_readiness_endpoint_returns_200_when_healthy(self, mock_db, mock_config):
        """Test that /health/ready returns 200 when healthy."""
        mock_db.return_value = {'status': 'ok'}
        mock_config.return_value = {'status': 'ok'}

        response = self.app.test_client().get('/health/ready')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    @mock.patch('mod_health.controllers.check_config')
    @mock.patch('mod_health.controllers.check_database')
    def test_readiness_endpoint_returns_503_when_unhealthy(self, mock_db, mock_config):
        """Test that /health/ready returns 503 when unhealthy."""
        mock_db.return_value = {'status': 'error', 'message': 'Connection failed'}
        mock_config.return_value = {'status': 'ok'}

        response = self.app.test_client().get('/health/ready')
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'unhealthy')


class TestHealthCheckFunctions(BaseTestCase):
    """Test individual health check functions."""

    def test_check_database_success(self):
        """Test check_database returns ok when database is accessible."""
        from mod_health.controllers import check_database
        with self.app.app_context():
            result = check_database()
            self.assertEqual(result['status'], 'ok')

    def test_check_database_failure(self):
        """Test check_database returns error when database fails."""
        from mod_health.controllers import check_database
        with self.app.app_context():
            # Mock at the source module where it's imported from
            with mock.patch('database.create_session') as mock_session:
                mock_session.side_effect = Exception('Connection refused')
                result = check_database()
                self.assertEqual(result['status'], 'error')
                # Generic message returned (actual exception logged server-side)
                self.assertEqual(result['message'], 'Database connection failed')

    def test_check_config_success(self):
        """Test check_config returns ok when config is complete."""
        from mod_health.controllers import check_config
        with self.app.app_context():
            # Set required config values for test
            self.app.config['GITHUB_TOKEN'] = 'test_token'
            result = check_config()
            self.assertEqual(result['status'], 'ok')

    def test_check_config_missing_keys(self):
        """Test check_config returns error when keys are missing."""
        from mod_health.controllers import check_config
        with self.app.app_context():
            # Ensure GITHUB_TOKEN is empty to trigger error
            self.app.config['GITHUB_TOKEN'] = ''
            result = check_config()
            self.assertEqual(result['status'], 'error')
            self.assertIn('GITHUB_TOKEN', result['message'])


class TestVersionEndpoint(BaseTestCase):
    """Test version endpoint."""

    @mock.patch('mod_health.controllers.get_git_info')
    def test_version_endpoint_returns_200_with_git_info(self, mock_git_info):
        """Test that /health/version returns 200 when git info is available."""
        mock_git_info.return_value = {
            'commit': 'abc123def456789012345678901234567890abcd',
            'short': 'abc123d',
            'branch': 'master',
        }

        response = self.app.test_client().get('/health/version')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertIn('timestamp', data)
        self.assertIn('git', data)
        self.assertEqual(data['git']['commit'], 'abc123def456789012345678901234567890abcd')
        self.assertEqual(data['git']['short'], 'abc123d')
        self.assertEqual(data['git']['branch'], 'master')

    @mock.patch('mod_health.controllers.get_git_info')
    def test_version_endpoint_returns_503_when_git_unavailable(self, mock_git_info):
        """Test that /health/version returns 503 when git info unavailable."""
        mock_git_info.return_value = {
            'commit': None,
            'short': None,
            'branch': None,
        }

        response = self.app.test_client().get('/health/version')
        self.assertEqual(response.status_code, 503)

        data = json.loads(response.data)
        self.assertIn('error', data)
        self.assertIn('git', data)
        self.assertIsNone(data['git']['commit'])


class TestGetGitInfo(BaseTestCase):
    """Test get_git_info function."""

    @mock.patch('subprocess.check_output')
    def test_get_git_info_success(self, mock_subprocess):
        """Test get_git_info returns correct values when git is available."""
        from mod_health.controllers import get_git_info

        # Mock both git commands
        mock_subprocess.side_effect = [
            b'abc123def456789012345678901234567890abcd\n',  # git rev-parse HEAD
            b'master\n',  # git rev-parse --abbrev-ref HEAD
        ]

        with self.app.app_context():
            result = get_git_info()

        self.assertEqual(result['commit'], 'abc123def456789012345678901234567890abcd')
        self.assertEqual(result['short'], 'abc123d')
        self.assertEqual(result['branch'], 'master')

    @mock.patch('subprocess.check_output')
    def test_get_git_info_git_not_available(self, mock_subprocess):
        """Test get_git_info handles missing git gracefully."""
        import subprocess

        from mod_health.controllers import get_git_info

        mock_subprocess.side_effect = FileNotFoundError('git not found')

        with self.app.app_context():
            result = get_git_info()

        self.assertIsNone(result['commit'])
        self.assertIsNone(result['short'])
        self.assertIsNone(result['branch'])

    @mock.patch('subprocess.check_output')
    def test_get_git_info_not_a_repo(self, mock_subprocess):
        """Test get_git_info handles non-repo directory gracefully."""
        import subprocess

        from mod_health.controllers import get_git_info

        mock_subprocess.side_effect = subprocess.CalledProcessError(128, 'git')

        with self.app.app_context():
            result = get_git_info()

        self.assertIsNone(result['commit'])
        self.assertIsNone(result['short'])
        self.assertIsNone(result['branch'])
