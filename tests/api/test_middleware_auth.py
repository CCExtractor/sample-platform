from flask import g

from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken
from mod_auth.models import Role, User
from tests.api.base import ApiTestCase


class TestMiddlewareAuth(ApiTestCase):
    def setUp(self):
        super().setUp()
        user = User('testuser1', Role.user, 'testuser1@local.com',
                    User.generate_hash('user123'))
        admin = User('testadmin1', Role.admin,
                     'testadmin1@local.com', User.generate_hash('admin123'))
        g.db.add_all([user, admin])
        g.db.commit()
        self.user = user
        self.admin = admin

    def generate_db_token(self, user, scopes=None, expires_in_days=7):
        plaintext = ApiToken.generate_token()
        token = ApiToken(
            user_id=user.id,
            token_name='test_token_' + ApiTestCase.create_random_string(8),
            token_hash=ApiToken.hash_token(plaintext),
            token_prefix=ApiToken.extract_prefix(plaintext),
            scopes=scopes or DEFAULT_SCOPES,
            expires_in_days=expires_in_days
        )
        g.db.add(token)
        g.db.commit()
        return plaintext, token

    def test_missing_auth_header(self):
        res = self.client.get('/api/v1/system/queue')
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json['code'], 'unauthorized')

    def test_invalid_auth_header_format(self):
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': 'InvalidFormat'})
        self.assertEqual(res.status_code, 401)

        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': 'Bearer '})
        self.assertEqual(res.status_code, 401)

    def test_invalid_token_prefix(self):
        res = self.client.get(
            '/api/v1/system/queue', headers={'Authorization': 'Bearer invalid_prefix_token'})
        self.assertEqual(res.status_code, 401)

    def test_token_not_found(self):
        res = self.client.get(
            '/api/v1/system/queue', headers={'Authorization': 'Bearer spci_faketoken1234567890'})
        self.assertEqual(res.status_code, 401)

    def test_wrong_hash(self):
        plaintext, token = self.generate_db_token(self.user)
        wrong_token = token.token_prefix + 'A' * \
            (len(plaintext) - len(token.token_prefix))
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {wrong_token}'})
        self.assertEqual(res.status_code, 401)

    def test_revoked_token(self):
        plaintext, token = self.generate_db_token(self.user)
        token.revoke()
        g.db.commit()
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 401)

    def test_expired_token(self):
        plaintext, _ = self.generate_db_token(self.user, expires_in_days=-1)
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 401)

    def test_valid_token_missing_scope(self):
        # /api/v1/system/queue requires 'system:read'
        plaintext, _ = self.generate_db_token(self.user, scopes=['runs:read'])
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 403)
        self.assertIn('code', res.json)
        self.assertEqual(res.json['code'], 'forbidden')
        self.assertIn('missing_scopes', res.json['details'])

    def test_valid_token_with_scope(self):
        plaintext, _ = self.generate_db_token(self.user, scopes=['system:read'])
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 200)

    def test_role_decorator_missing_role(self):
        # GET /api/v1/auth/tokens requires 'tokens:manage' and roles ['admin', 'contributor', 'tester']
        plaintext, _ = self.generate_db_token(
            self.user, scopes=['tokens:manage'])  # role is user
        res = self.client.get('/api/v1/auth/tokens',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json['code'], 'forbidden')

    def test_role_decorator_with_role(self):
        plaintext, _ = self.generate_db_token(
            self.admin, scopes=['tokens:manage'])  # role is admin
        res = self.client.get('/api/v1/auth/tokens',
                              headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 200)

    def test_scope_boundary_write_endpoints_fail_on_read_only_scopes(self):
        plaintext, _ = self.generate_db_token(
            self.user, scopes=['runs:read', 'results:read'])

        # 1. POST /runs
        res = self.client.post(
            '/api/v1/runs', headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json['code'], 'forbidden')

        # 2. POST /runs/1/cancel
        res = self.client.post('/api/v1/runs/1/cancel',
                               headers={'Authorization': f'Bearer {plaintext}'})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json['code'], 'forbidden')

    def test_multiple_candidates_same_prefix(self):
        plaintext1, token1 = self.generate_db_token(self.user, scopes=['system:read'])
        plaintext2, token2 = self.generate_db_token(self.user, scopes=['system:read'])

        # Force same prefix, must start with spci_ and be 16 chars long for extract_prefix
        prefix = 'spci_abc12345678'
        token1.token_prefix = prefix
        token2.token_prefix = prefix
        g.db.commit()

        # Modify plaintexts to have the same prefix
        submitted1 = prefix + plaintext1[len(prefix):]
        submitted2 = prefix + plaintext2[len(prefix):]

        token1.token_hash = ApiToken.hash_token(submitted1)
        token2.token_hash = ApiToken.hash_token(submitted2)
        g.db.commit()

        # It should correctly match token2 and ignore token1
        res = self.client.get('/api/v1/system/queue',
                              headers={'Authorization': f'Bearer {submitted2}'})
        self.assertEqual(res.status_code, 200)

        # Invalid token with same prefix
        submitted3 = prefix + 'A' * 32
        res3 = self.client.get(
            '/api/v1/system/queue', headers={'Authorization': f'Bearer {submitted3}'})
        self.assertEqual(res3.status_code, 401)

    def test_auth_sets_g_api_user_and_token(self):
        plaintext, token = self.generate_db_token(self.user, scopes=['system:read'])
        expected_user_id = self.user.id
        expected_token_id = token.id
        with self.app.test_request_context('/api/v1/system/queue', headers={'Authorization': f'Bearer {plaintext}'}):
            # This triggers all before_request handlers, including authenticate_request
            resp = self.app.preprocess_request()
            # If rate limit isn't cleared, it might return 429, but it is cleared in setUp
            self.assertIsNone(resp)
            self.assertEqual(g.api_user.id, expected_user_id)
            self.assertEqual(g.api_token.id, expected_token_id)
