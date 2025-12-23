"""Tests for the health check endpoints."""

import json
from unittest import mock

from tests.base import BaseTestCase


class TestHealthEndpoints(BaseTestCase):
    """Test health check endpoints."""

    def test_health_endpoint_returns_200_when_healthy(self):
        """Test that /health returns 200 when all checks pass."""
        response = self.app.test_client().get('/health')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')
        self.assertIn('timestamp', data)
        self.assertIn('checks', data)
        self.assertEqual(data['checks']['database']['status'], 'ok')
        self.assertEqual(data['checks']['config']['status'], 'ok')

    def test_health_endpoint_returns_503_when_database_fails(self):
        """Test that /health returns 503 when database check fails."""
        with mock.patch('mod_health.controllers.check_database') as mock_db:
            mock_db.return_value = {'status': 'error', 'message': 'Connection failed'}
            response = self.app.test_client().get('/health')
            self.assertEqual(response.status_code, 503)

            data = json.loads(response.data)
            self.assertEqual(data['status'], 'unhealthy')
            self.assertEqual(data['checks']['database']['status'], 'error')

    def test_health_endpoint_returns_503_when_config_fails(self):
        """Test that /health returns 503 when config check fails."""
        with mock.patch('mod_health.controllers.check_config') as mock_config:
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

    def test_readiness_endpoint_returns_200_when_healthy(self):
        """Test that /health/ready returns 200 when healthy."""
        response = self.app.test_client().get('/health/ready')
        self.assertEqual(response.status_code, 200)

        data = json.loads(response.data)
        self.assertEqual(data['status'], 'healthy')

    def test_readiness_endpoint_returns_503_when_unhealthy(self):
        """Test that /health/ready returns 503 when unhealthy."""
        with mock.patch('mod_health.controllers.check_database') as mock_db:
            mock_db.return_value = {'status': 'error', 'message': 'Connection failed'}
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
            with mock.patch('mod_health.controllers.create_session') as mock_session:
                mock_session.side_effect = Exception('Connection refused')
                result = check_database()
                self.assertEqual(result['status'], 'error')
                self.assertIn('Connection refused', result['message'])

    def test_check_config_success(self):
        """Test check_config returns ok when config is complete."""
        from mod_health.controllers import check_config
        with self.app.app_context():
            result = check_config()
            self.assertEqual(result['status'], 'ok')

    def test_check_config_missing_keys(self):
        """Test check_config returns error when keys are missing."""
        from mod_health.controllers import check_config
        with self.app.app_context():
            # Temporarily remove a required key
            original_value = self.app.config.get('GITHUB_TOKEN')
            self.app.config['GITHUB_TOKEN'] = ''
            result = check_config()
            self.assertEqual(result['status'], 'error')
            self.assertIn('GITHUB_TOKEN', result['message'])
            # Restore
            self.app.config['GITHUB_TOKEN'] = original_value
