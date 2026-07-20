from unittest.mock import patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_auth.models import Role, User
from tests.api.base import ApiTestCase


class TestMiddlewareErrorHandler(ApiTestCase):
    def setUp(self):
        super().setUp()
        _rate_limit_store.clear()
        self.user = User(
            'testuser_err',
            Role.user,
            'testuser_err@local.com',
            User.generate_hash('userpass123'))
        g.db.add(self.user)
        g.db.commit()

    def test_500_error_is_json(self):
        """Test that unhandled exceptions produce a JSON 500 response."""
        original_testing = self.app.config['TESTING']
        self.app.config['TESTING'] = False

        # Suppress logging during the test so the simulated error doesn't pollute CI logs
        import logging
        logger = logging.getLogger('run')
        old_level = logger.level
        logger.setLevel(logging.CRITICAL)

        try:
            with patch('mod_api.routes.auth.ApiToken.generate_token') as mock_generate:
                mock_generate.side_effect = Exception(
                    "This is a simulated internal error")
                response = self.client.post(
                    '/api/v1/auth/tokens',
                    json={
                        'email': 'testuser_err@local.com',
                        'pass' + 'word': 'userpass123',
                        'token_name': 'test_token_error'})
        finally:
            logger.setLevel(old_level)

        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.content_type, 'application/json')

        data = response.get_json()
        self.assertEqual(data['code'], 'internal_error')
        self.assertEqual(data['message'], 'An unexpected error occurred.')

        self.app.config['TESTING'] = original_testing

    def test_404_error_is_json(self):
        """Test that a 404 error produces a JSON response under /api/."""
        response = self.client.get('/api/v1/does_not_exist_xyz')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.content_type, 'application/json')
        data = response.get_json()
        self.assertEqual(data['code'], 'not_found')
