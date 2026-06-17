import json
from datetime import datetime, timedelta

from flask import g

from mod_api.models.api_token import DEFAULT_SCOPES, ApiToken
from mod_auth.models import Role, User
from tests.base import BaseTestCase


class TestModelsApiToken(BaseTestCase):
    def setUp(self):
        super().setUp()
        user = User('testuser1', Role.user, 'testuser1@local.com',
                    User.generate_hash('user123'))
        g.db.add(user)
        g.db.commit()
        self.user_id = user.id

    def test_api_token_creation_and_hashing(self):
        plaintext = ApiToken.generate_token()
        self.assertTrue(plaintext.startswith('spci_'))

        token_hash = ApiToken.hash_token(plaintext)
        self.assertTrue(ApiToken.verify_token(plaintext, token_hash))
        self.assertFalse(ApiToken.verify_token('spci_wrongtoken', token_hash))

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
