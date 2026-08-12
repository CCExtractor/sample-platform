import json
import time
from unittest.mock import patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_api.models.api_token import ApiToken
from mod_auth.models import Role, User
from tests.api.base import ApiTestCase

PWD_KEY = 'pass' + 'word'


class TestRoutesAuth(ApiTestCase):
    def setUp(self):
        super().setUp()
        # Create user
        self.user = User(
            'testuser_auth',
            Role.contributor,
            'auth_user@local.com',
            User.generate_hash('userpass123'))
        self.admin = User(
            'testadmin_auth',
            Role.admin,
            'auth_admin@local.com',
            User.generate_hash('adminpass123'))
        g.db.add_all([self.user, self.admin])
        g.db.commit()
        self.user_id = self.user.id
        _rate_limit_store.clear()

    def get_token(self, email, pwd, token_name='test_token', scopes=None):
        payload = {
            'email': email,
            PWD_KEY: pwd,
            'token_name': token_name
        }
        if scopes:
            payload['scopes'] = scopes

        res = self.client.post(
            '/api/v1/auth/tokens',
            data=json.dumps(payload),
            content_type='application/json')
        return res

    def test_create_token_success(self):
        res = self.get_token('auth_user@local.com', 'userpass123', 'token1')
        self.assertEqual(res.status_code, 201)
        self.assertIn('token', res.json)
        self.assertEqual(res.json['token_name'], 'token1')

        # Verify in DB
        token_db = ApiToken.query.filter_by(token_name='token1').first()
        self.assertIsNotNone(token_db)
        self.assertEqual(token_db.user_id, self.user_id)

    def test_create_token_invalid_credentials(self):
        # Invalid email
        res = self.get_token('wrong@local.com', 'userpass123', 'token1')
        self.assertEqual(res.status_code, 401)

        # Invalid password
        res = self.get_token('auth_user@local.com', 'wrongpass', 'token1')
        self.assertEqual(res.status_code, 401)

    def test_create_token_invalid_scopes_for_role(self):
        # Contributor role shouldn't be able to request 'baselines:write'
        res = self.get_token('auth_user@local.com', 'userpass123',
                             'token_baselines', ['baselines:write'])
        self.assertEqual(res.status_code, 403)
        self.assertIn('forbidden', res.json['code'])

    def test_create_token_admin_can_request_baselines_write(self):
        # Admin role should be able to request 'baselines:write'
        res = self.get_token('auth_admin@local.com', 'adminpass123',
                             'admin_baselines', ['baselines:write'])
        self.assertEqual(res.status_code, 201)
        self.assertIn('baselines:write', res.json['scopes'])

    def test_create_token_duplicate_name(self):
        self.get_token('auth_user@local.com', 'userpass123', 'duplicate')
        res = self.get_token('auth_user@local.com', 'userpass123', 'duplicate')
        self.assertEqual(res.status_code, 400)
        self.assertIn('validation_error', res.json['code'])

    def test_create_token_integrity_error_mock(self):
        with patch('sqlalchemy.orm.Session.commit') as mock_commit:
            from sqlalchemy.exc import IntegrityError
            mock_commit.side_effect = IntegrityError(
                "UNIQUE constraint failed: api_token.user_id, api_token.token_name",
                "params",
                "orig")
            res = self.get_token('auth_user@local.com',
                                 'userpass123', 'token_integ')
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

    def test_revoke_current_token(self):
        res_create = self.get_token(
            'auth_user@local.com',
            'userpass123',
            'to_revoke',
            scopes=['runs:read'])
        token_str = res_create.json['token']

        res_revoke = self.client.delete(
            '/api/v1/auth/tokens/current',
            headers={
                'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_revoke.status_code, 204)

        # Check DB
        token_db = ApiToken.query.filter_by(token_name='to_revoke').first()
        self.assertTrue(token_db.is_revoked)

        # Trying to use it again should fail
        res_fail = self.client.get(
            '/api/v1/auth/tokens',
            headers={
                'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_fail.status_code, 401)

    def test_revoke_current_token_no_manage_scope(self):
        # Self-revocation is intentionally scope-free; any token can revoke itself
        res_create = self.get_token(
            'auth_user@local.com',
            'userpass123',
            'to_revoke_no_scope',
            scopes=['results:read'])
        token_str = res_create.json['token']

        res = self.client.delete(
            '/api/v1/auth/tokens/current',
            headers={
                'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 204)

        res_fail = self.client.get(
            '/api/v1/auth/tokens',
            headers={
                'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_fail.status_code, 401)

    def test_revoke_current_token_missing(self):
        res = self.client.delete('/api/v1/auth/tokens/current')
        self.assertEqual(res.status_code, 401)

    def test_list_tokens(self):
        # Listing tokens requires 'tokens:manage' scope, which is restricted to admins
        res1 = self.get_token('auth_admin@local.com',
                              'adminpass123', 't1', scopes=['tokens:manage'])
        _ = self.get_token('auth_admin@local.com', 'adminpass123', 't2')
        token_str = res1.json['token']

        res = self.client.get('/api/v1/auth/tokens',
                              headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 2)
        token_names = [item['token_name'] for item in res.json['data']]
        self.assertIn('t1', token_names)
        self.assertIn('t2', token_names)

    def test_list_tokens_all_admin(self):
        self.get_token('auth_user@local.com', 'userpass123', 'user_token')
        admin_res = self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            'admin_token',
            scopes=['tokens:manage'])
        admin_token = admin_res.json['token']

        res = self.client.get(
            '/api/v1/auth/tokens?all=true',
            headers={
                'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 2)
        token_names = [item['token_name'] for item in res.json['data']]
        self.assertIn('user_token', token_names)
        self.assertIn('admin_token', token_names)

    def test_revoke_specific_token(self):
        # User creates two tokens
        res1 = self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            't1_spec',
            scopes=['tokens:manage'])
        self.get_token('auth_admin@local.com', 'adminpass123', 't2_spec')
        token_str = res1.json['token']

        token_db = ApiToken.query.filter_by(token_name='t2_spec').first()
        token_id = token_db.id

        res = self.client.delete(
            f'/api/v1/auth/tokens/{token_id}',
            headers={
                'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 204)

        token_db_after = ApiToken.query.filter_by(id=token_id).first()
        self.assertTrue(token_db_after.is_revoked)

    def test_revoke_specific_token_not_found(self):
        res1 = self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            't1_spec2',
            scopes=['tokens:manage'])
        token_str = res1.json['token']

        res = self.client.delete(
            '/api/v1/auth/tokens/999',
            headers={
                'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 404)

    def test_list_tokens_does_not_expose_plaintext(self):
        res1 = self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            't_expose',
            scopes=['tokens:manage'])
        token_str = res1.json['token']

        res = self.client.get('/api/v1/auth/tokens',
                              headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 200)
        for item in res.json['data']:
            self.assertNotIn('token', item)
            self.assertNotIn('token_prefix', item)

    def test_admin_can_revoke_other_users_token(self):
        # User B creates a token
        user_b = User('user_b', Role.contributor,
                      'user_b@local.com', User.generate_hash('userpass123'))
        g.db.add(user_b)
        g.db.commit()
        _ = self.get_token(
            'user_b@local.com', 'userpass123', 'tok_b_admin')
        token_b_db = ApiToken.query.filter_by(token_name='tok_b_admin').first()
        token_b_id = token_b_db.id

        # Admin gets a token
        res_admin = self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            'tok_admin',
            scopes=['tokens:manage'])
        admin_token = res_admin.json['token']

        # Admin revokes user B's token -> 204
        res = self.client.delete(
            f'/api/v1/auth/tokens/{token_b_id}',
            headers={
                'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res.status_code, 204)
        token_db_after = ApiToken.query.filter_by(id=token_b_id).first()
        self.assertTrue(token_db_after.is_revoked)

    def test_create_token_invalid_name_pattern(self):
        payload = {'email': 'auth_user@local.com',
                   PWD_KEY: 'userpass123', 'token_name': 'has spaces!'}
        res = self.client.post(
            '/api/v1/auth/tokens',
            data=json.dumps(payload),
            content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_create_token_max_expiry_enforced(self):
        payload = {'email': 'auth_user@local.com', PWD_KEY: 'userpass123',
                   'token_name': 'valid_name', 'expires_in_days': 31}
        res = self.client.post(
            '/api/v1/auth/tokens',
            data=json.dumps(payload),
            content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_create_token_rejects_extra_fields(self):
        payload = {
            'email': 'auth_user@local.com',
            PWD_KEY: 'userpass123',
            'token_name': 'valid_name',
            'injected_field': 'malicious_value'
        }
        res = self.client.post(
            '/api/v1/auth/tokens',
            data=json.dumps(payload),
            content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_list_tokens_user_role_blocked(self):
        # A plain user role (User.user) tries to list tokens
        plain_user = User(
            'plain_user',
            Role.user,
            'plain@local.com',
            User.generate_hash('userpass123'))
        g.db.add(plain_user)
        g.db.commit()
        # They can create a token...
        res_create = self.get_token(
            'plain@local.com', 'userpass123', 'my_token')
        plain_token = res_create.json['token']

        # ...but they cannot list them (403 due to require_roles)
        res_list = self.client.get(
            '/api/v1/auth/tokens',
            headers={
                'Authorization': f'Bearer {plain_token}'})
        self.assertEqual(res_list.status_code, 403)
        self.assertEqual(res_list.json['code'], 'forbidden')

    def test_revoke_specific_token_already_revoked(self):
        # Admin creates an auth token and a separate token to revoke
        res_admin = self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            'tok_admin_auth',
            scopes=['tokens:manage'])
        admin_token = res_admin.json['token']

        self.get_token(
            'auth_admin@local.com',
            'adminpass123',
            'tok_to_revoke',
            scopes=['tokens:manage'])
        token_db = ApiToken.query.filter_by(token_name='tok_to_revoke').first()
        token_id = token_db.id

        # First revocation
        res1 = self.client.delete(
            f'/api/v1/auth/tokens/{token_id}',
            headers={
                'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res1.status_code, 204)

        # Second revocation should be idempotent (204)
        res2 = self.client.delete(
            f'/api/v1/auth/tokens/{token_id}',
            headers={
                'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res2.status_code, 204)

    def test_get_current_user_returns_role_and_scopes(self):
        token = self.get_token(
            'auth_user@local.com', 'userpass123', 'me_tok',
            scopes=['runs:read']).json['token']

        res = self.client.get(
            '/api/v1/auth/me',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['user_id'], self.user_id)
        self.assertEqual(res.json['email'], 'auth_user@local.com')
        # The role comes from the account, never from what the client asked
        # for; this is what the web console gates its UI on.
        self.assertEqual(res.json['role'], 'contributor')
        self.assertEqual(res.json['scopes'], ['runs:read'])

    def test_get_current_user_reports_admin_role(self):
        token = self.get_token(
            'auth_admin@local.com', 'adminpass123', 'me_admin',
            scopes=['runs:read']).json['token']

        res = self.client.get(
            '/api/v1/auth/me',
            headers={'Authorization': f'Bearer {token}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['role'], 'admin')

    def test_get_current_user_requires_a_token(self):
        res = self.client.get('/api/v1/auth/me')
        self.assertEqual(res.status_code, 401)

    def _admin_token(self, name='usr_admin'):
        return self.get_token('auth_admin@local.com', 'adminpass123', name,
                              scopes=['tokens:manage']).json['token']

    def _patch_user(self, token, user_id, body):
        return self.client.patch(
            f'/api/v1/users/{user_id}',
            data=json.dumps(body),
            content_type='application/json',
            headers={'Authorization': f'Bearer {token}'})

    def test_list_users(self):
        res = self.client.get(
            '/api/v1/users',
            headers={'Authorization': f'Bearer {self._admin_token()}'})

        self.assertEqual(res.status_code, 200)
        row = next(r for r in res.json['data']
                   if r['email'] == 'auth_admin@local.com')
        self.assertEqual(row['role'], 'admin')
        self.assertFalse(row['github_linked'])
        # Credentials must never appear in the payload.
        self.assertNotIn('password', row)
        self.assertNotIn('github_token', row)

    def test_list_users_is_paginated(self):
        res = self.client.get(
            '/api/v1/users?limit=1&offset=0',
            headers={'Authorization': f'Bearer {self._admin_token("usr_p")}'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 1)
        # total counts every user, not just the page, so a client knows to
        # keep paging instead of silently seeing the first page only.
        self.assertGreaterEqual(res.json['pagination']['total'], 2)

    def test_list_users_forbidden_for_contributor(self):
        token = self.get_token('auth_user@local.com', 'userpass123',
                               'usr_c', scopes=['runs:read']).json['token']
        res = self.client.get(
            '/api/v1/users', headers={'Authorization': f'Bearer {token}'})
        self.assertEqual(res.status_code, 403)

    def test_update_user_role(self):
        res = self._patch_user(self._admin_token('usr_up'), self.user_id,
                               {'role': 'user'})

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['role'], 'user')
        self.assertEqual(
            User.query.filter(User.id == self.user_id).first().role, Role.user)

    def test_update_user_role_rejects_self(self):
        admin_id = User.query.filter(
            User.email == 'auth_admin@local.com').first().id
        res = self._patch_user(self._admin_token('usr_self'), admin_id,
                               {'role': 'user'})

        # Demoting yourself would leave nobody able to undo it.
        self.assertEqual(res.status_code, 403)
        self.assertEqual(
            User.query.filter(User.id == admin_id).first().role, Role.admin)

    def test_update_user_role_invalid_role(self):
        res = self._patch_user(self._admin_token('usr_bad'), self.user_id,
                               {'role': 'superuser'})
        self.assertEqual(res.status_code, 400)

    def test_update_user_role_unknown_user(self):
        res = self._patch_user(self._admin_token('usr_404'), 999999,
                               {'role': 'user'})
        self.assertEqual(res.status_code, 404)

    # ---- account: signup, reset, self-service, deactivate --------------

    def _json(self, method, path, body, headers=None):
        return getattr(self.client, method)(
            f'/api/v1{path}', data=json.dumps(body),
            content_type='application/json', headers=headers or {})

    @patch('requests.post')
    def test_signup_sends_a_link(self, post):
        res = self._json('post', '/auth/signup',
                         {'email': 'brand_new@local.com'})

        self.assertEqual(res.status_code, 202)
        self.assertTrue(post.called)

    @patch('requests.post')
    def test_signup_is_silent_about_existing_accounts(self, post):
        known = self._json('post', '/auth/signup',
                           {'email': 'auth_user@local.com'})
        _rate_limit_store.clear()
        unknown = self._json('post', '/auth/signup',
                             {'email': 'nobody@local.com'})

        # Same status and body either way, or the reply becomes a way to
        # ask whether an address has an account.
        self.assertEqual(known.status_code, unknown.status_code)
        self.assertEqual(known.json, unknown.json)

    @patch('requests.post')
    def test_password_reset_request_is_silent_about_unknown_email(self, post):
        res = self._json('post', '/auth/password-reset',
                         {'email': 'nobody@local.com'})

        self.assertEqual(res.status_code, 202)
        self.assertFalse(post.called)

    @patch('requests.post')
    def test_password_reset_request_sends_to_a_known_address(self, post):
        # Exercises the path that actually builds and sends the link, which
        # an unknown-address test never reaches.
        res = self._json('post', '/auth/password-reset',
                         {'email': 'auth_user@local.com'})

        self.assertEqual(res.status_code, 202)
        self.assertTrue(post.called)

    @patch('requests.post')
    def test_reset_link_points_at_these_pages_without_a_console(self, post):
        from run import app

        with patch.dict(app.config, {'CONSOLE_URL': ''}):
            self._json('post', '/auth/password-reset',
                       {'email': 'auth_user@local.com'})

        body = str(post.call_args)
        self.assertIn('/account/reset/', body)

    @patch('requests.post')
    def test_reset_link_points_at_the_console_when_one_is_configured(
            self, post):
        from run import app

        with patch.dict(app.config,
                        {'CONSOLE_URL': 'https://console.example.org/'}):
            self._json('post', '/auth/password-reset',
                       {'email': 'auth_user@local.com'})

        body = str(post.call_args)
        # One slash, and the three values the console posts back.
        self.assertIn('https://console.example.org/reset?uid=', body)
        self.assertIn('expires=', body)
        self.assertIn('mac=', body)

    @patch('requests.post')
    def test_password_reset_completes_with_a_valid_link(self, post):
        from mod_auth.controllers import generate_hmac_hash
        from run import app

        expires = int(time.time()) + 600
        content = f'{self.user_id}|{expires}|{self.user.password}'
        mac = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content)

        res = self._json('post', '/auth/password-reset/complete', {
            'user_id': self.user_id,
            'expires': expires,
            'mac': mac,
            'password': 'a-brand-new-password',
        })

        self.assertEqual(res.status_code, 200)
        changed = User.query.filter_by(id=self.user_id).first()
        self.assertTrue(changed.is_password_valid('a-brand-new-password'))

    def test_password_reset_rejects_a_forged_mac(self):
        res = self._json('post', '/auth/password-reset/complete', {
            'user_id': self.user_id,
            'expires': int(time.time()) + 600,
            'mac': 'not-the-real-signature',
            'password': 'a-brand-new-password',
        })

        self.assertEqual(res.status_code, 400)
        unchanged = User.query.filter_by(id=self.user_id).first()
        self.assertTrue(unchanged.is_password_valid('userpass123'))

    def test_password_reset_rejects_an_expired_link(self):
        from mod_auth.controllers import generate_hmac_hash
        from run import app

        expires = int(time.time()) - 1
        content = f'{self.user_id}|{expires}|{self.user.password}'
        mac = generate_hmac_hash(app.config.get('HMAC_KEY', ''), content)

        res = self._json('post', '/auth/password-reset/complete', {
            'user_id': self.user_id,
            'expires': expires,
            'mac': mac,
            'password': 'a-brand-new-password',
        })

        self.assertEqual(res.status_code, 400)

    def _auth(self, email='auth_user@local.com', pwd='userpass123',
              name='acct', scopes=None):
        # get_token returns the response in this class, not the token.
        token = self.get_token(email, pwd, name, scopes=scopes).json['token']
        return {'Authorization': f'Bearer {token}'}

    def test_update_own_name(self):
        res = self._json('patch', '/auth/me', {'name': 'Renamed'},
                         self._auth(name='acct1'))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['name'], 'Renamed')

    def test_changing_password_requires_the_current_one(self):
        res = self._json('patch', '/auth/me',
                         {'new_password': 'something-else-entirely'},
                         self._auth(name='acct2'))

        self.assertEqual(res.status_code, 403)

    def test_change_password_with_the_current_one(self):
        res = self._json('patch', '/auth/me', {
            'current_password': 'userpass123',
            'new_password': 'something-else-entirely',
        }, self._auth(name='acct3'))

        self.assertEqual(res.status_code, 200)
        changed = User.query.filter_by(id=self.user_id).first()
        self.assertTrue(changed.is_password_valid('something-else-entirely'))

    def test_change_email_to_one_already_taken(self):
        res = self._json('patch', '/auth/me', {
            'current_password': 'userpass123',
            'email': 'auth_admin@local.com',
        }, self._auth(name='acct4'))

        self.assertEqual(res.status_code, 409)

    def test_deactivate_own_account(self):
        # A plain contributor can never hold tokens:manage, so closing your
        # own account has to work without it.
        res = self.client.post(
            f'/api/v1/users/{self.user_id}/deactivate',
            headers=self._auth(name='acct5'))

        self.assertEqual(res.status_code, 200)
        gone = User.query.filter_by(id=self.user_id).first()
        self.assertEqual(gone.name, f'Anonymous {self.user_id}')

    def test_deactivate_someone_else_needs_admin(self):
        res = self.client.post(
            f'/api/v1/users/{self.user_id}/deactivate',
            headers=self._auth('auth_admin@local.com', 'adminpass123',
                               'acct6'))

        self.assertEqual(res.status_code, 200)
        gone = User.query.filter_by(id=self.user_id).first()
        self.assertEqual(gone.name, f'Anonymous {self.user_id}')
        self.assertFalse(gone.is_password_valid('userpass123'))

    def test_deactivate_requires_admin_or_ownership(self):
        res = self.client.post(
            f'/api/v1/users/{self.admin.id}/deactivate',
            headers=self._auth(name='acct7'))

        self.assertEqual(res.status_code, 403)

    def test_deactivation_revokes_the_accounts_tokens(self):
        # A token the account already holds, minted before anyone reaches
        # for deactivation.
        victim = self._auth(name='doomed')

        res = self.client.post(
            f'/api/v1/users/{self.user_id}/deactivate',
            headers=self._auth('auth_admin@local.com', 'adminpass123',
                               'deact_admin'))

        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.json['tokens_revoked'], 1)
        self.assertTrue(all(
            t.is_revoked for t in
            ApiToken.query.filter(ApiToken.user_id == self.user_id).all()))
        # And the token stops working straight away, not at its expiry.
        after = self.client.get('/api/v1/auth/me', headers=victim)
        self.assertEqual(after.status_code, 401)

    def test_deactivating_someone_else_leaves_the_admin_working(self):
        admin_headers = self._auth('auth_admin@local.com', 'adminpass123',
                                   'deact_admin2')

        self.client.post(f'/api/v1/users/{self.user_id}/deactivate',
                         headers=admin_headers)

        still_fine = self.client.get('/api/v1/auth/me', headers=admin_headers)
        self.assertEqual(still_fine.status_code, 200)

    def test_ftp_credentials_need_a_write_scope(self):
        # A working credential for the ingest server is not something a
        # read-only token should be able to fetch.
        res = self.client.get(
            '/api/v1/auth/me/ftp-credentials',
            headers=self._auth(name='ftp_ro', scopes=['results:read']))

        self.assertEqual(res.status_code, 403)

    def test_get_single_user(self):
        res = self.client.get(
            f'/api/v1/users/{self.user_id}',
            headers=self._auth('auth_admin@local.com', 'adminpass123',
                               'one_user', scopes=['tokens:manage']))

        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json['user_id'], self.user_id)

    @patch('requests.post')
    def test_admin_can_send_someone_a_reset_link(self, post):
        res = self.client.post(
            f'/api/v1/users/{self.user_id}/password-reset',
            headers=self._auth('auth_admin@local.com', 'adminpass123',
                               'reset_other'))

        self.assertEqual(res.status_code, 202)
        self.assertTrue(post.called)

    @patch('requests.post')
    def test_reset_link_for_someone_else_needs_admin(self, post):
        res = self.client.post(
            f'/api/v1/users/{self.admin.id}/password-reset',
            headers=self._auth(name='reset_forbidden'))

        self.assertEqual(res.status_code, 403)
        self.assertFalse(post.called)

    def test_ftp_credentials_are_created_on_first_ask(self):
        # Asked for with the scope an uploader would hold; the default set
        # is read-only and is refused, which the test below covers.
        res = self.client.get(
            '/api/v1/auth/me/ftp-credentials',
            headers=self._auth(name='ftp1', scopes=['runs:write']))

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json['username'])
        self.assertTrue(res.json['password'])

        # Asking twice returns the same pair rather than rotating them.
        again = self.client.get(
            '/api/v1/auth/me/ftp-credentials',
            headers=self._auth(name='ftp2', scopes=['runs:write']))
        self.assertEqual(again.json['username'], res.json['username'])

    def test_github_link_reports_status_without_the_token(self):
        user = User.query.filter(User.id == self.user_id).first()
        user.github_token = 'gho_secret_value'
        user.github_login = 'someone'
        g.db.commit()

        res = self.client.get(
            '/api/v1/auth/me/github', headers=self._auth(name='gh1'))

        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json['linked'])
        self.assertEqual(res.json['github_login'], 'someone')
        # The stored token must never travel back out, under any key.
        self.assertNotIn('gho_secret_value', res.get_data(as_text=True))
        # The URL to start a connection carries nothing secret either.
        self.assertIn('github.com/login/oauth/authorize',
                      res.json['authorize_url'])
        self.assertNotIn('client_secret', res.json['authorize_url'])

    def test_github_unlink_forgets_the_connection(self):
        user = User.query.filter(User.id == self.user_id).first()
        user.github_token = 'gho_secret_value'
        user.github_login = 'someone'
        g.db.commit()

        res = self.client.delete(
            '/api/v1/auth/me/github', headers=self._auth(name='gh2'))

        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.json['linked'])

        user = User.query.filter(User.id == self.user_id).first()
        self.assertIsNone(user.github_token)
        self.assertIsNone(user.github_login)

    def test_github_endpoints_need_a_token(self):
        self.assertEqual(self.client.get('/api/v1/auth/me/github').status_code,
                         401)
        self.assertEqual(
            self.client.delete('/api/v1/auth/me/github').status_code, 401)
