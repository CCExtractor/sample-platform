from unittest.mock import patch

from flask import g

from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken
from mod_auth.models import Role, User
from tests.api.base import ApiTestCase


class TestModelsApiToken(ApiTestCase):
    def setUp(self):
        super().setUp()

        # Mock token hashing to speed up tests and avoid SonarCloud crypto warnings
        self._hash_patcher = patch(
            'mod_api.models.api_token.ApiToken.hash_token',
            side_effect=lambda t: f'mock_hash_{t}'
        )
        self._verify_patcher = patch(
            'mod_api.models.api_token.ApiToken.verify_token',
            side_effect=lambda t, h: h == f'mock_hash_{t}'
        )
        self._hash_patcher.start()
        self._verify_patcher.start()

        user = User('testuser1', Role.user, 'testuser1@local.com',
                    User.generate_hash('user123'))
        g.db.add(user)
        g.db.commit()
        self.user_id = user.id

    def tearDown(self):
        self._hash_patcher.stop()
        self._verify_patcher.stop()
        super().tearDown()

    def test_api_token_creation_and_hashing(self):
        plaintext = ApiToken.generate_token()
        self.assertTrue(plaintext.startswith('spci_'))

        token_hash = ApiToken.hash_token(plaintext)
        self.assertTrue(ApiToken.verify_token(plaintext, token_hash))
        self.assertFalse(ApiToken.verify_token('spci_wrongtoken', token_hash))

    def test_invalid_scope_raises(self):
        with self.assertRaises(ValueError):
            ApiToken(
                user_id=self.user_id,
                token_name='bad_token',
                token_hash='mock',
                token_prefix='spci_xxx',
                scopes=['admin:nuke_everything'],
            )

    def test_api_token_properties(self):
        plaintext = ApiToken.generate_token()
        token = ApiToken(
            user_id=self.user_id,
            token_name='my_token',
            token_hash=ApiToken.hash_token(plaintext),
            token_prefix=ApiToken.extract_prefix(plaintext),
            scopes=DEFAULT_SCOPES,
            expires_in_days=7
        )
        g.db.add(token)
        g.db.commit()

        self.assertTrue(token.is_valid)
        self.assertFalse(token.is_revoked)
        self.assertFalse(token.is_expired)
        self.assertEqual(token.token_prefix,
                         ApiToken.extract_prefix(plaintext))

        # Check has_scope
        self.assertTrue(token.has_scope('runs:read'))
        self.assertFalse(token.has_scope('admin:all'))

        # Revoke
        token.revoke()
        g.db.commit()
        self.assertFalse(token.is_valid)
        self.assertTrue(token.is_revoked)

    def test_token_expiration(self):
        plaintext = ApiToken.generate_token()
        token = ApiToken(
            user_id=self.user_id,
            token_name='expiring_token',
            token_hash=ApiToken.hash_token(plaintext),
            token_prefix=ApiToken.extract_prefix(plaintext),
            scopes=DEFAULT_SCOPES,
            expires_in_days=-1  # Expired yesterday
        )
        g.db.add(token)
        g.db.commit()

        self.assertTrue(token.is_expired)
        self.assertFalse(token.is_valid)
