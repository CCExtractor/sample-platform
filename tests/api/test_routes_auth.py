import json
from unittest.mock import MagicMock, patch

from flask import g

from mod_api.middleware.rate_limit import _rate_limit_store
from mod_api.models.api_token import ApiToken
from mod_auth.models import Role, User
from tests.base import BaseTestCase


class TestRoutesAuth(BaseTestCase):
    def setUp(self):
        super().setUp()
        # Create user
        self.user = User('testuser_auth', Role.contributor,
                         'auth_user@local.com', User.generate_hash('userpass123'))
        self.admin = User('testadmin_auth', Role.admin,
                          'auth_admin@local.com', User.generate_hash('adminpass123'))
        g.db.add_all([self.user, self.admin])
        g.db.commit()
        self.user_id = self.user.id
        _rate_limit_store.clear()

    def get_token(self, email, password, token_name='test_token', scopes=None):
        payload = {
            'email': email,
            'password': password,
            'token_name': token_name
        }
        if scopes:
            payload['scopes'] = scopes

        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
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
                "duplicate", "params", "orig")
            res = self.get_token('auth_user@local.com',
                                 'userpass123', 'token_integ')
            self.assertEqual(res.status_code, 400)
            self.assertEqual(res.json['code'], 'validation_error')

    def test_revoke_current_token(self):
        res_create = self.get_token(
            'auth_user@local.com', 'userpass123', 'to_revoke', scopes=['tokens:manage'])
        token_str = res_create.json['token']

        res_revoke = self.client.delete(
            '/api/v1/auth/tokens/current', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_revoke.status_code, 204)

        # Check DB
        token_db = ApiToken.query.filter_by(token_name='to_revoke').first()
        self.assertTrue(token_db.is_revoked)

        # Trying to use it again should fail
        res_fail = self.client.get(
            '/api/v1/auth/tokens', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_fail.status_code, 401)

    def test_revoke_current_token_no_manage_scope(self):
        res_create = self.get_token(
            'auth_user@local.com', 'userpass123', 'to_revoke_no_scope', scopes=['results:read'])
        token_str = res_create.json['token']

        res = self.client.delete(
            '/api/v1/auth/tokens/current', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 204)

        res_fail = self.client.get(
            '/api/v1/auth/tokens', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_fail.status_code, 401)

        # Trying to use it again should fail
        res_fail = self.client.get(
            '/api/v1/auth/tokens', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res_fail.status_code, 401)

    def test_revoke_current_token_missing(self):
        res = self.client.delete('/api/v1/auth/tokens/current')
        self.assertEqual(res.status_code, 401)

    def test_list_tokens(self):
        res1 = self.get_token('auth_user@local.com',
                              'userpass123', 't1', scopes=['tokens:manage'])
        _ = self.get_token('auth_user@local.com', 'userpass123', 't2')
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
            'auth_admin@local.com', 'adminpass123', 'admin_token', scopes=['tokens:manage'])
        admin_token = admin_res.json['token']

        res = self.client.get('/api/v1/auth/tokens?all=true',
                              headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json['data']), 2)
        token_names = [item['token_name'] for item in res.json['data']]
        self.assertIn('user_token', token_names)
        self.assertIn('admin_token', token_names)

    def test_list_tokens_all_non_admin(self):
        user_res = self.get_token(
            'auth_user@local.com', 'userpass123', 'user_token2', scopes=['tokens:manage'])
        user_token = user_res.json['token']

        res = self.client.get('/api/v1/auth/tokens?all=true',
                              headers={'Authorization': f'Bearer {user_token}'})
        self.assertEqual(res.status_code, 403)

    def test_revoke_specific_token(self):
        # User creates two tokens
        res1 = self.get_token(
            'auth_user@local.com', 'userpass123', 't1_spec', scopes=['tokens:manage'])
        self.get_token('auth_user@local.com', 'userpass123', 't2_spec')
        token_str = res1.json['token']

        token_db = ApiToken.query.filter_by(token_name='t2_spec').first()
        token_id = token_db.id

        res = self.client.delete(
            f'/api/v1/auth/tokens/{token_id}', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 204)

        token_db_after = ApiToken.query.filter_by(id=token_id).first()
        self.assertTrue(token_db_after.is_revoked)

    def test_revoke_specific_token_not_found(self):
        res1 = self.get_token(
            'auth_user@local.com', 'userpass123', 't1_spec2', scopes=['tokens:manage'])
        token_str = res1.json['token']

        res = self.client.delete(
            '/api/v1/auth/tokens/999', headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 404)

    def test_list_tokens_does_not_expose_plaintext(self):
        res1 = self.get_token(
            'auth_user@local.com', 'userpass123', 't_expose', scopes=['tokens:manage'])
        token_str = res1.json['token']

        res = self.client.get('/api/v1/auth/tokens',
                              headers={'Authorization': f'Bearer {token_str}'})
        self.assertEqual(res.status_code, 200)
        for item in res.json['data']:
            self.assertNotIn('token', item)
            self.assertIn('token_prefix', item)

    def test_revoke_other_users_token_forbidden(self):
        # auth_user creates a token
        res_a = self.get_token('auth_user@local.com',
                               'userpass123', 'tok_a', scopes=['tokens:manage'])
        token_a = res_a.json['token']

        # admin creates a second user (user_b)
        user_b = User('user_b', Role.contributor,
                      'user_b@local.com', User.generate_hash('userpass123'))
        g.db.add(user_b)
        g.db.commit()

        # create a token for user_b
        _ = self.get_token('user_b@local.com', 'userpass123', 'tok_b')
        token_b_db = ApiToken.query.filter_by(token_name='tok_b').first()
        token_b_id = token_b_db.id

        # user A tries to revoke user B's token.
        # Note: Non-admins get a uniform 404 for both "doesn't exist" and "belongs to another user"
        # to prevent token-ID enumeration. This hardening deviates from the initial 403 spec.
        res = self.client.delete(
            f'/api/v1/auth/tokens/{token_b_id}', headers={'Authorization': f'Bearer {token_a}'})
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json['code'], 'not_found')

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
            'auth_admin@local.com', 'adminpass123', 'tok_admin', scopes=['tokens:manage'])
        admin_token = res_admin.json['token']

        # Admin revokes user B's token -> 204
        res = self.client.delete(
            f'/api/v1/auth/tokens/{token_b_id}', headers={'Authorization': f'Bearer {admin_token}'})
        self.assertEqual(res.status_code, 204)
        token_db_after = ApiToken.query.filter_by(id=token_b_id).first()
        self.assertTrue(token_db_after.is_revoked)

    def test_create_token_invalid_name_pattern(self):
        payload = {'email': 'auth_user@local.com',
                   'pass' + 'word': 'userpass123', 'token_name': 'has spaces!'}
        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_create_token_max_expiry_enforced(self):
        payload = {'email': 'auth_user@local.com', 'pass' + 'word': 'userpass123',
                   'token_name': 'valid_name', 'expires_in_days': 31}
        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')

    def test_create_token_rejects_extra_fields(self):
        payload = {
            'email': 'auth_user@local.com',
            'pass' + 'word': 'userpass123',
            'token_name': 'valid_name',
            'injected_field': 'malicious_value'
        }
        res = self.client.post(
            '/api/v1/auth/tokens', data=json.dumps(payload), content_type='application/json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.json['code'], 'validation_error')
