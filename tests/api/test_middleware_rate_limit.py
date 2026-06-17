import time

from flask import g

from mod_api.middleware.rate_limit import _EVICTION_INTERVAL, _rate_limit_store
from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken
from mod_auth.models import Role, User
from tests.base import BaseTestCase


class TestMiddlewareRateLimit(BaseTestCase):
    def setUp(self):
        super().setUp()
        user = User('testuser1', Role.user, 'testuser1@local.com',
                    User.generate_hash('password123'))
        g.db.add(user)
        g.db.commit()
        self.user = user
        from mod_api.middleware.rate_limit import _rate_limit_store
        _rate_limit_store.clear()

    def get_token(self, scopes=None):
        plaintext = ApiToken.generate_token()
        token = ApiToken(
            user_id=self.user.id,
            token_name='test_token_' + BaseTestCase.create_random_string(8),
            token_hash=ApiToken.hash_token(plaintext),
            token_prefix=ApiToken.extract_prefix(plaintext),
            scopes=scopes if scopes is not None else DEFAULT_SCOPES,
            expires_in_days=7
        )
        g.db.add(token)
        g.db.commit()
        token_id = token.id
        return plaintext, token_id

    def test_evict_stale_entries(self):
        # We manipulate the internal state to test eviction logic
        import mod_api.middleware.rate_limit as rl
        rl._rate_limit_store.clear()
        rl._eviction_counter = _EVICTION_INTERVAL - 1

        # Add a stale entry
        stale_time = time.time() - 1000  # > 900 seconds
        rl._rate_limit_store['stale_key'] = {
            'count': 1, 'window_start': stale_time}

        # Add a fresh entry
        fresh_time = time.time()
        rl._rate_limit_store['fresh_key'] = {
            'count': 1, 'window_start': fresh_time}

        # This request triggers eviction
        self.client.get('/api/v1/system/health')

        # Stale key should be removed, fresh key remains
        self.assertNotIn('stale_key', rl._rate_limit_store)
        self.assertIn('fresh_key', rl._rate_limit_store)

    def test_get_client_ip_forwarded(self):
        # Because run.py uses ProxyFix, X-Forwarded-For overrides the REMOTE_ADDR
        # to the rightmost IP in the header list.
        res = self.client.get(
            '/api/v1/system/health', headers={'X-Forwarded-For': '192.168.1.1, 10.0.0.1'})
        self.assertEqual(res.status_code, 200)
        from mod_api.middleware.rate_limit import _rate_limit_store
        self.assertIn('ip:10.0.0.1', _rate_limit_store)

    def test_rate_limit_window_reset(self):
        import time

        import mod_api.middleware.rate_limit as rl
        rl._rate_limit_store.clear()

        # Simulate an entry that has expired its window
        stale_time = time.time() - 61  # slightly more than 60s window
        rl._rate_limit_store['ip:127.0.0.1'] = {
            'count': 20, 'window_start': stale_time}

        # Since the window has expired, this request should succeed and reset the count
        res = self.client.get('/api/v1/system/health')
        self.assertEqual(res.status_code, 200)

        # The store should now show count=1 with a new window start
        self.assertEqual(rl._rate_limit_store['ip:127.0.0.1']['count'], 1)
        self.assertGreater(
            rl._rate_limit_store['ip:127.0.0.1']['window_start'], stale_time)

    def test_rate_limit_separate_keys_per_token(self):
        import mod_api.middleware.rate_limit as rl
        rl._rate_limit_store.clear()

        plaintext1, t1_id = self.get_token(scopes=['system:read'])
        plaintext2, t2_id = self.get_token(scopes=['system:read'])

        # Request with first token
        self.client.get('/api/v1/system/queue',
                        headers={'Authorization': f'Bearer {plaintext1}'})
        # Request with second token
        self.client.get('/api/v1/system/queue',
                        headers={'Authorization': f'Bearer {plaintext2}'})

        # Both should be tracked separately
        self.assertIn(f'token:{t1_id}', rl._rate_limit_store)
        self.assertIn(f'token:{t2_id}', rl._rate_limit_store)
        self.assertEqual(rl._rate_limit_store[f'token:{t1_id}']['count'], 1)
        self.assertEqual(rl._rate_limit_store[f'token:{t2_id}']['count'], 1)

    def test_rate_limit_headers(self):
        import mod_api.middleware.rate_limit as rl
        rl._rate_limit_store.clear()

        res = self.client.get('/api/v1/system/health')
        self.assertEqual(res.status_code, 200)
        self.assertIn('X-RateLimit-Limit', res.headers)
        self.assertIn('X-RateLimit-Remaining', res.headers)
        self.assertIn('X-RateLimit-Reset', res.headers)
        # GET method limit
        self.assertEqual(res.headers['X-RateLimit-Limit'], '120')

    def test_rate_limit_post_auth(self):
        rl_store = __import__('mod_api.middleware.rate_limit', fromlist=[
                              '_rate_limit_store'])._rate_limit_store
        rl_store.clear()

        # token creation has a limit of 5
        # The schema might require valid token_name without spaces.
        # User 'testuser1@local.com' must exist and have correct password.
        payload = {'email': 'testuser1@local.com',
                   'password': 'password123', 'token_name': 'test_token'}
        res = self.client.post('/api/v1/auth/tokens', json=payload)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.headers['X-RateLimit-Limit'], '5')

    def test_rate_limit_authenticated(self):
        rl_store = __import__('mod_api.middleware.rate_limit', fromlist=[
                              '_rate_limit_store'])._rate_limit_store
        rl_store.clear()

        plaintext, token_id = self.get_token(scopes=['system:read'])
        # Make a request using token
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 200)

        # Find key with token_id
        key = f'token:{token_id}'
        self.assertIn(key, rl_store)

    def test_rate_limit_exceeded_auth(self):
        rl_store = __import__('mod_api.middleware.rate_limit', fromlist=[
                              '_rate_limit_store'])._rate_limit_store
        rl_store.clear()
        payload = {'email': 'testuser1@local.com',
                   'password': 'password123', 'token_name': 'test'}

        for i in range(5):
            payload['token_name'] = f'test{i}'
            self.client.post('/api/v1/auth/tokens', json=payload)

        payload['token_name'] = 'test5'
        res = self.client.post('/api/v1/auth/tokens', json=payload)
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.headers['X-RateLimit-Remaining'], '0')
