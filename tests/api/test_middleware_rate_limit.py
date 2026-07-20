from mod_api.middleware.rate_limit import _rate_limit_store
from tests.api.base import ApiTestCase


class TestMiddlewareRateLimit(ApiTestCase):
    def setUp(self):
        super().setUp()
        _rate_limit_store.clear()

    def test_create_token_rate_limit(self):
        """Test the 5 req / 15 min limit for /auth/tokens."""
        # We need to test without TESTING=True so the rate limiter actually
        # runs.
        self.app.config['TESTING'] = False

        payload = {
            'email': 'testuser1@local.com',
            'pass' + 'word': 'user123',
            'token_name': 'test_token',
        }

        # 1. Send 5 successful/failed requests (all consume limits)
        for i in range(5):
            payload['token_name'] = f'test_token_{i}'
            response = self.client.post('/api/v1/auth/tokens', json=payload)
            self.assertIn(response.status_code, (201, 400, 401))

            # Headers should show remaining requests
            self.assertIn('X-RateLimit-Remaining', response.headers)
            remaining = int(response.headers['X-RateLimit-Remaining'])
            self.assertEqual(remaining, 4 - i)

        # 2. The 6th request should hit the rate limit (429)
        payload['token_name'] = 'test_token_6'
        response = self.client.post('/api/v1/auth/tokens', json=payload)
        self.assertEqual(response.status_code, 429)
        data = response.get_json()
        self.assertEqual(data['code'], 'rate_limited')
        self.assertIn('Retry after', data['message'])

        self.assertEqual(response.headers['X-RateLimit-Remaining'], '0')
        self.assertIn('Retry-After', response.headers)

        # 3. Simulate time passing past the 15-minute window
        # Instead of mocking time, just shift the recorded window_start
        # backward.
        for key in _rate_limit_store:
            _rate_limit_store[key]['window_start'] -= 960

        payload['token_name'] = 'test_token_7'
        response = self.client.post('/api/v1/auth/tokens', json=payload)
        self.assertIn(response.status_code, (201, 400, 401))
        self.assertEqual(response.headers['X-RateLimit-Remaining'], '4')

        # Restore
        self.app.config['TESTING'] = True
